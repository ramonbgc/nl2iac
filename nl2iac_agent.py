"""Imports"""
#import logging
import re
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

RESOURCES = "\nUse just resources from the following list: google_compute_address, google_compute_attached_disk, google_compute_autoscaler, google_compute_backend_bucket, google_compute_backend_bucket_signed_url_key, google_compute_backend_service, google_compute_backend_service_signed_url_key, google_compute_disk, google_compute_disk_async_replication, google_compute_disk_iam_binding, google_compute_disk_iam_member, google_compute_disk_iam_policy, google_compute_disk_resource_policy_attachment, google_compute_external_vpn_gateway, google_compute_firewall, google_compute_firewall_policy, google_compute_firewall_policy_association, google_compute_firewall_policy_rule, google_compute_forwarding_rule, google_compute_global_address, google_compute_global_forwarding_rule, google_compute_global_network_endpoint, google_compute_global_network_endpoint_group, google_compute_ha_vpn_gateway, google_compute_health_check, google_compute_http_health_check, google_compute_https_health_check, google_compute_image, google_compute_image_iam_binding, google_compute_image_iam_member, google_compute_image_iam_policy, google_compute_instance, google_compute_instance_from_template, google_compute_instance_group, google_compute_instance_group_manager, google_compute_instance_group_membership, google_compute_instance_group_named_port, google_compute_instance_iam_binding, google_compute_instance_iam_member, google_compute_instance_iam_policy, google_compute_instance_settings, google_compute_instance_template, google_compute_interconnect_attachment, google_compute_managed_ssl_certificate, google_compute_network, google_compute_network_endpoint, google_compute_network_endpoint_group, google_compute_network_endpoints, google_compute_network_firewall_policy, google_compute_network_firewall_policy_association, google_compute_network_firewall_policy_rule, google_compute_network_peering, google_compute_network_peering_routes_config, google_compute_node_group, google_compute_node_template, google_compute_packet_mirroring, google_compute_per_instance_config, google_compute_project_default_network_tier, google_compute_project_metadata, google_compute_project_metadata_item, google_compute_public_advertised_prefix, google_compute_public_delegated_prefix, google_compute_region_autoscaler, google_compute_region_backend_service, google_compute_region_commitment, google_compute_region_disk, google_compute_region_disk_iam_binding, google_compute_region_disk_iam_member, google_compute_region_disk_iam_policy, google_compute_region_disk_resource_policy_attachment, google_compute_region_health_check, google_compute_region_instance_group_manager, google_compute_region_instance_template, google_compute_region_network_endpoint, google_compute_region_network_endpoint_group, google_compute_region_network_firewall_policy, google_compute_region_network_firewall_policy_association, google_compute_region_network_firewall_policy_rule, google_compute_region_per_instance_config, google_compute_region_ssl_certificate, google_compute_region_ssl_policy, google_compute_region_target_http_proxy, google_compute_region_target_https_proxy, google_compute_region_target_tcp_proxy, google_compute_region_url_map, google_compute_reservation, google_compute_resource_policy, google_compute_route, google_compute_router, google_compute_router_interface, google_compute_router_nat, google_compute_router_peer, google_compute_security_policy, google_compute_security_policy_rule, google_compute_service_attachment, google_compute_shared_vpc_host_project, google_compute_shared_vpc_service_project, google_compute_snapshot, google_compute_snapshot_iam_binding, google_compute_snapshot_iam_member, google_compute_snapshot_iam_policy, google_compute_ssl_certificate, google_compute_ssl_policy, google_compute_subnetwork, google_compute_subnetwork_iam_binding, google_compute_subnetwork_iam_member, google_compute_subnetwork_iam_policy, google_compute_target_grpc_proxy, google_compute_target_http_proxy, google_compute_target_https_proxy, google_compute_target_instance, google_compute_target_pool, google_compute_target_ssl_proxy, google_compute_target_tcp_proxy, google_compute_url_map, google_compute_vpn_gateway, google_compute_vpn_tunnel"

# prompts
PROMPT_TERRAFORM_DEVELOPER = """
  You're a seasoned Terraform developer being able to get information from terraform commands, identify the terraform resources involved in a solution design and to generate terraform templates.
  You never make assumptions and always use the tools you have available.
  Your goal is to generate a terraform template based on the solution description provided by the user.
  
  Follow this guidelines when generating the template:
    - Always include the provider section at the begining. The values must be filled with the values in the Configuration section.
    - Be careful with arguments referencing other arguments. Be sure all the references have been declared previously.
    - Return syntactically and semantically correct Terraform templates being able to pass a terraform validate and terraform plan execution.
    - Always add firewall rules for ssh connectivity.
    - Use the last available image for Google Compute instances boot_disk if no one is provided.
    - Google copmpute instances names must be always lowercase.
    - Explicitely always include the value 'false' for the 'auto_create_subnetworks' for Google Compute Network when created.
    - The output must be ONLY the correct template in plain text without any additional comment.
    - Don't output ```hcl, ```terraform nor ```.

  """ + RESOURCES

PROMPT_TERRAFORM_VALIDATOR = """
  You're a Terraform developer guru working in terraform code validation.
  You never guess the answer as all your validations are based on function calling.
  You always take the time to double-check your work, so try a second validation after the first confirmation.
  Provide only one result at the end of all validtions the output is always a valid json with three elements: valid (use exactly True or False), errors (if any, just a list of plain text errors) and suggestions (a list of suggestions on how to improve the solution based on best practices and similar solutions.)
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
    HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
  }

  match provider_id.lower():
    case 'google':
      if model_type == 'chat':
        model = ChatVertexAI(model_name=model_id, temperature=temperature,
                            project=project_id, location=region_id,
                            convert_system_message_to_human = False,
                            safety_settings=safety_settings,
                            streaming = True,
                            request_parallelism = 1,
                            #max_output_tokens = 8192,
                            verbose=True)
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
  executor = AgentExecutor(agent=agent, tools=agent_tools, return_intermediate_steps=True,
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
  """Validates a terraform template using the 'terraform plan' command.

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
  tools = [terraform_template_plan, terraform_template_validate]
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
