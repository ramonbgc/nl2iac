"""Imports"""
#import logging
import subprocess
import json
# langchain
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
# Google
from langchain_google_vertexai import ChatVertexAI, VertexAI, HarmBlockThreshold, HarmCategory
# OpenAI
from langchain_openai import ChatOpenAI, OpenAI


##################
# terraform
TERRAFORM_VALIDATE = ["terraform", "validate", "-no-color"]
TERRAFORM_PLAN = ["terraform", "plan", "-no-color"]
TERRAFORM_APPLY = ["terraform", "apply", "-auto-approve"]
TERRAFORM_RESOURCES_DESCRIPTION = ["terraform", "providers", "schema", "-json"]
TERRAFORM_RESOURCES_FILTER = ['google_compute_']
# logging
LOGGING_FORMAT = "[%(asctime)s %(filename)s->%(funcName)s():%(lineno)s]%(levelname)s: %(message)s"

# prompts
PROMPT_TERRAFORM_DEVELOPER = """
  You're a Terraform seasoned developer being able to get information from terraform commands, to identify the terraform resources involved in a solution design, and to generate terraform templates.
  Always follow all these steps to the end:
    1: Get a list of the allowed resources for the provider.
    2: Identify all the Google cloud components mentioned on the solution provided by the user.
    3: Create a list of mandatory attributes' rules needed for the resources and include them on the terraform template.
    4: Generate a valid terraform template.
  
  When generating the terraform template to implement the solution described by the user following these guidelines:
    - Always incluide the provider section at the begining. The values must be filled with the values on the Configuration section.
    - Be careful with arguments referencing other arguments. Be sure all the references have been declared previously.
    - Return syntactically and semantically correct Terraform templates being able to pass a terraform validate execution.
    - Follow the instructions on the required arguments for every resource used.
    - Use the last available image for Google Compute instances boot_disk if no one is provided.
    - Google copmpute instances names must be always lowercase.
    - Always add firewall rules for ssh connectivity.
    - Explicitely always include the value 'false' for the 'auto_create_subnetworks' for Google Compute Network when created.
    - Explicitely specify subnetworks.
    - The output must be ONLY the correct template without any additional comment
    - Don't output ```hcl, ```terraform nor ```.
  """

PROMPT_TERRAFORM_VALIDATOR = """
  You're a principal Google cloud terraform developer. 
  Your work is to detect if the provided Terraform template is totally correct and could pass a terraform validation and be executed without errors.
  You can also provide suggestions to improve the template based on what other similar solutions implement.

  Guidelines:
  - Check that no references are being included without an origin value on the template.
  - Check that all the values provided are correct for the Google provider.
  - Check that all the required arguments indicated are included on the template.
  - To be considered valid a Terraform template must be correct, follow all the rules from the HCL language and be able to pass correctly the terraform validate and terraform plan command execution.
  - Based on the user description find suggestions about other components that can be added to improve the solution performance and security.
  - Respond always using a valid python dict format with three elements: valid (use exactly True or False), errors (if any) and suggestions (a list of suggestions).
  - Respond just with the valid JSON, don't add any other text. In the JSON data format, the keys must be enclosed in double quotes. Document must start with LEFT CURLY BRACKET character and end with the RIGHT CURLY BRACKET character
  - The output must be just the JSON described above and cannot contain ```json nor ```.
  """

PROMPT_TERRAFORM_DEPLOYER = """
  You're a terraform guru and Google Cloud infra admin. 
  Your work is to deploy terraform templates in Google Cloud.
  Deploy the terraform templates using the tools you have available.

  Guidelines:
  - Respond always using a valid json with three elements: valid (use exactly True or False), suggestions (if any error is detected analyze it and provide a list of suggestions to solve it) and errors (a list of errors if any)
  - Respond just with the valid json, don't add any other additional text.
  """

#######################################################
#######################################################
# external functions
#######################################################
def terraform_commands(command, command_type='exec'):
  """checking with Terraform validate if the template is ok."""
  terraform_execution = subprocess.run(command, capture_output=True, check=False)
  #logger.debug(terraform_execution.stdout.decode())
  if command_type == 'exec':
    if terraform_execution.returncode != 0:
      val = terraform_execution.stderr.decode().replace('\n\n', '.').replace('\n', '')
    else:
      val = ""
  else:
    val = terraform_execution.stdout.decode()

  return val


def get_available_terraform_resources(output_type: str):
  """Get the resources available for the terraform provider executing 
      the command: terraform providers schema -json
      Returns a list or a dict based on output_type
  """
  #logger.debug('Getting the resources available for the provider')
  # getting the full list from terraform command as a dict
  res_list_str = terraform_commands(TERRAFORM_RESOURCES_DESCRIPTION, 'desc')
  provider_resources_dict = json.loads(res_list_str)['provider_schemas']\
    ['registry.terraform.io/hashicorp/google']['resource_schemas']

  # getting list of resources taking care of filters
  output = ''
  to_del = []
  for resource in provider_resources_dict:
    if any(f in resource for f in TERRAFORM_RESOURCES_FILTER):
      output += resource + ', '
    else:
      to_del.append(resource)

  if output_type == "dict":
    # deleting not needed resources
    for k in to_del:
      del provider_resources_dict[k]
    #returning a dict with all of the resources' properties
    return provider_resources_dict

  #returning a list with just the names
  return output


#################################################
## helper functions
#################################################
def clean_str(text: str) -> str:
  """Cleaning the string outputs from the model"""
  return text.\
    replace("```hcl", "").\
      replace("```python", "").\
        replace("```json", "").\
          replace("```", "").\
            replace("\\n", "\n")


def create_model(provider_id, model_id, temperature, region_id, project_id, model_type='chat'):
  """creating the model to be used."""
  # security settings default to NONE as we're not processing sensitive data
  safety_settings = {
    HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
  }

  match provider_id.lower():
    case 'google':
      if model_type == 'chat':
        model = ChatVertexAI(model_name=model_id, temperature=temperature,
                            project=project_id, location=region_id,
                            convert_system_message_to_human = False,
                            safety_settings=safety_settings,
                            streaming = False,
                            max_retries = 3,
                            request_parallelism = 2,
                            #api_transport = 'rest',
                            #max_output_tokens = 8192,
                            verbose=False)
      else:
        model = VertexAI(model_name=model_id, temperature=temperature,
                            project=project_id, location=region_id,
                            convert_system_message_to_human = False,
                            safety_settings=safety_settings,
                            verbose=True)
    case 'openai':
      if model_type == 'chat':
        model = ChatOpenAI(model_name=model_id, temperature=temperature,
                          verbose=True)
      else:
        model = OpenAI(model_name=model_id, temperature=temperature,
                          verbose=True)

  return model


def create_agent(llm_model, agent_tools, system):
  """creating an agent working node with a name and tools."""
  prompt = ChatPromptTemplate.from_messages(
    [
      SystemMessage(content=system),
      MessagesPlaceholder(variable_name="user_message"),
      MessagesPlaceholder(variable_name="agent_scratchpad")
    ]
  )
  # creating the agent and the executor with the tools
  agent = create_tool_calling_agent(llm=llm_model, tools=agent_tools, prompt=prompt)
  executor = AgentExecutor(agent=agent, tools=agent_tools, return_intermediate_steps=False,
                           verbose=True, early_stopping_method='forced')
  return executor


#################################################
## Tools for the agents
#################################################
@tool
def get_provider_resources() -> dict:
  """Return a list of allowed resources by the provider to be used on the templates.
  """
  #logger.info('(tool) Getting a list of the resources')
  output = get_available_terraform_resources("list")
  #logger.debug('(tool) Provider resources: %s', output)
  # returning a string with the resources
  return {'available_resources': output}


@tool
def get_required_arguments_list(resources_names: str) -> dict:
  """ Creates a list of mandatory attributes rules needed for the resources in use.
      Use it when you already have identified the resources involved to add to the terraform template as rules.
      Returns a string with rules about the required attributes for every resources

      Args:
        resources_names: a python list formated string with the terraform resources already identified.
  """
  # creating a list os resources
  #logger.debug('Input string. resources_names: %s', resources_names)
    # taking care of wrong inputs
  resources_names.replace("'", '"')
  if "[" not in resources_names:
    resources_names = '[' + resources_names + ']'

  list_resources = json.loads(resources_names)
  # getting REQUIRED arguments and blocks for every resource
  # calling the aux function
  resources_dict = get_available_terraform_resources("dict")
  output = ''
  for resource in list_resources:
    res = [a for a, obj in (
      resources_dict[resource]['block']['block_types']).items()
      if 'min_items' in obj]
    res += [a for a, obj in (
      resources_dict[resource]['block']['attributes']).items()
      if 'required' in obj]
    output += '\nresource ' + resource + ' mandatory requires ' + ','.join(res) + ' as arguments.'
    # some blocks have required arguments
    blocks_required_arguments = [(k, k2)  for k, v in (
      resources_dict[resource]['block']['block_types']).items()
      for k2, v2 in v['block']['attributes'].items() if 'required' in v2 ]
    if blocks_required_arguments:
      for block, argument in blocks_required_arguments:
        output += 'If Block ' + block + ' is being used within ' \
          + resource + ' it mandatory requires ' + argument + ' argument.'

  return {'attributes_rules': output}


@tool
def terraform_template_validate(terraform_template: str) -> dict:
  """Validates a terraform template using the 'terraform validate' command.

      Args:
        terraform_template: A string containing the terraform template to be validated.
  """
  #logger.info('terraform_template_validation EXECUTION')
  # to use terraform validate a file must be created on the local system
  cleaned_terraform_template = terraform_template.replace("\\\\n", "\n").replace('\\"', '"')
  with open("main.tf", "w", encoding="utf-8") as file_template:
    file_template.write(clean_str(cleaned_terraform_template))

  validation_errors = terraform_commands(TERRAFORM_VALIDATE)
  if validation_errors != '':
    return {'validation_errors_terraform': validation_errors }

  return {'validation_errors_terraform': None}


@tool
def terraform_template_plan(terraform_template: str) -> dict:
  """Validates if a terraform template is correct using the 'terraform plan' command.

      Args:
        terraform_template: A string containing the terraform template to be validated.
  """
  #logger.info('terraform_template_validation EXECUTION')
  # to use terraform validate a file must be created on the local system
  cleaned_terraform_template = terraform_template.replace("\\\\n", "\n").replace('\\"', '"')
  with open("main.tf", "w", encoding="utf-8") as file_template:
    file_template.write(clean_str(cleaned_terraform_template))

  validation_errors = terraform_commands(TERRAFORM_PLAN)
  if validation_errors != '':
    return {'validation_errors_terraform': validation_errors }

  return {'validation_errors_terraform': None}


@tool
def terraform_apply():
  """ Deploy an already created main.tf template using the 'Terraform Apply' command.
  """
  #logger.info('terraform_apply EXECUTION')
  # getting the full list from terraform command as a dict
  deployment_errors = terraform_commands(TERRAFORM_APPLY)
  return {'deployment_errors' : deployment_errors}


#################################################
# agents
#################################################
def terraform_developer_agent(provider_id, model_id, temperature, project_id, region_id):
  """Terraform developer agent designed to identify components and resources and generate templates."""
  llm = create_model(provider_id, model_id, temperature, project_id=project_id, region_id=region_id)
  tools = [get_provider_resources, get_required_arguments_list]
  agent = create_agent(llm_model=llm, agent_tools=tools,system=PROMPT_TERRAFORM_DEVELOPER)
  return agent


def terraform_validator_agent(provider_id, model_id, temperature, project_id, region_id):
  """Terraform agent designed to validate and suggest improvements an already generated template."""
  llm = create_model(provider_id, model_id, temperature, project_id=project_id, region_id=region_id)
  tools = [terraform_template_validate, terraform_template_plan]
  agent = create_agent(llm_model=llm, agent_tools=tools, system=PROMPT_TERRAFORM_VALIDATOR)
  return agent


def terraform_deployer_agent(provider_id, model_id, temperature, project_id, region_id):
  """Terraform agent designed to deploy the already generated and validated template."""
  llm = create_model(provider_id, model_id, temperature, project_id=project_id, region_id=region_id)
  tools = [terraform_apply]
  agent = create_agent(llm_model=llm, agent_tools=tools, system=PROMPT_TERRAFORM_DEPLOYER)
  return agent
# logger = logging.getLogger(__name__)
# logging.basicConfig(format=LOGGING_FORMAT, level=logging.INFO)
