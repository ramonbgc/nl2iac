"""Imports"""
import os
import json
import base64
import shutil
#from vertexai.preview.generative_models import Image
from datetime import datetime
from PIL import Image
import streamlit as st
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_community.callbacks.streamlit import StreamlitCallbackHandler
from langsmith import Client
import nl2iac_agent

##################
# variables
PROJECT_ID = "rgc-tfg-uoc"
REGION = "us-central1"
# models
GOOGLE_MODEL_ID = "gemini-1.5-pro-preview-0409"
OPENAI_MODEL_ID = "gpt-4-turbo"
TEMPERATURE = 0.2
#PRIMARY_MODEL_ID = "gemini-1.0-pro-002"
SECONDARY_MODEL_ID = "code-bison"
# generals
MAX_RETRIES = 3
DEPLOY_INFRA = False
# prompt
PROMPT_IDENTIFY_GCP_COMPONENTS_FROM_IMAGE = """
  You are a Google cloud architect guru. Your job is to create a text describing the components represented on the provided image.

  Guidelines:
  - Identify all the Google cloud components drawn in the image.
  - Be as concrete as possible with the configurations and parameters.
  - The output must be a plain text without format that describes the components and properties represented in the image.
  - Append the provided Configuration in the output as well.

  """

##################
# system variables
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "nl2IaC"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = st.secrets['LANGCHAIN_API_KEY']  # Update to your API key

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = '/home/mon/rgc-tfg-uoc-3a70fbac5ccd.json'

if "parameters" not in st.session_state:
  st.session_state["parameters"] = f"""\nConfiguration:\nproject: {PROJECT_ID}, region: {REGION}\n"""
if "user_prompt" not in st.session_state:
  st.session_state["user_prompt"] = """Create two Compute Engine instance with debian images.
  The name of the instance are rgc-vm-xx where xx is a two digit sequential number.
  Create a network and subnetwork specific for this vm, name it rgc-net-01"""


#######################################################
#######################################################
# functions
#######################################################
def add_status_message(status_message, message_type, save=True):
  """Add a message to he status tab"""
  if save:
    st.session_state['history_status_message'].append((status_message, message_type))
  # adding timestamp
  status_message = datetime.now().strftime("%H:%M:%S") + ' ' + status_message
  match message_type:
    case 'info':
      status_tab_cont.info(status_message, icon="ℹ️")
    case 'success':
      status_tab_cont.success(status_message, icon="✅")
    case 'warning':
      status_tab_cont.warning(status_message, icon="⚠️")
    case 'error':
      status_tab_cont.error(status_message, icon="🚨")


def upload_image_and_generate_description():
  """Uploading an image to be processed."""
  file_base64 = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
  if ('file_base64' not in st.session_state) or (file_base64 != st.session_state['file_base64']):
    st.session_state['image'] = Image.open(uploaded_file)
    add_status_message("Image uplodaded", 'info')
    # if an image is being used a description must be obtained
    image_message =  {
      "type": "image_url",
      "image_url": {"url": f"""data:image/jpeg;base64,
                    {file_base64}"""},
    }
    text_message = {
        "type": "text",
        "text": PROMPT_IDENTIFY_GCP_COMPONENTS_FROM_IMAGE + '\nConfiguration:\n' + st.session_state["parameters"],
    }
    content = [image_message, text_message]
    message = [HumanMessage(content=content)]
    image_description = st.session_state['tf_developer_agent'].invoke(
      {'user_message': message},
      config=st.session_state['cfg'])
    st.session_state['solution_description'] = image_description['output']
    add_status_message("Image description generated", 'info')

    # saving the file for later checks
    st.session_state['file_base64'] = file_base64

  else:
    add_status_message("File unchanged, no need to generate a description again.", 'info')


def generate_template():
  """Generating a candidate template with the info provided."""
  if (uploaded_file) or (user_input != ''):
    if uploaded_file is None:
      st.session_state['solution_description'] = user_input + '\nConfiguration:\n' + st.session_state["parameters"]

    message = [HumanMessage(content=st.session_state['solution_description'] +
                            st.session_state.get('previous_error', ''))]
    # if the template hasn't been already generated
    if 'candidate_terraform_template' not in st.session_state:
      st.session_state['candidate_terraform_template'] = st.session_state['tf_developer_agent'].invoke(
        {'user_message': message},
        config=st.session_state['cfg'])
      add_status_message("Candidate template generated", 'info')
  else:
    add_status_message("Provide a text or a file describing the architecture of the solution", 'error')


def validate_template():
  """Validating the template."""
  if ('tf_validation' not in st.session_state) or (st.session_state['tf_validation']['valid'] is not True):
    # validating the generated template
    # preparing the callback between streamlit and langchain to provide feedback
    st.session_state['terraform_template_validation'] = st.session_state['tf_validation_agent'].invoke(
      {'user_message': [HumanMessage(
        content='Template to check:\n' + st.session_state['candidate_terraform_template']['output'])]},
        config=st.session_state['cfg'])

    st.session_state['tf_validation'] = json.loads(st.session_state['terraform_template_validation']['output'])
    st.session_state['tf_validation_valid'] = st.session_state['tf_validation']['valid']
    code_expander_label = 'Generated Template ' + str(st.session_state.get('validate_retry_number', ''))
    code_expander_expanded = True
    st.session_state['code_exp'] = state_cont.expander(code_expander_label, expanded=code_expander_expanded)
    if st.session_state['tf_validation_valid'] is True:
      del st.session_state['validate_retry_number']
      # showing suggestions if available
      add_status_message("Template validated.", 'success')
      # creating the container to show the template and suggestions
      # showing suggestions if any
      if st.session_state['tf_validation']['suggestions']:
        st.session_state['tf_validation_suggestions'] = "\n".join(st.session_state['tf_validation']['suggestions'])
        st.session_state['code_exp'].info(
          f"Improvement suggestions for the solution:\n {st.session_state['tf_validation_suggestions']}",
          icon="ℹ️")
      st.session_state['terraform_template'] = st.session_state['candidate_terraform_template']
      # showing the validate template
      st.session_state['code_exp'].code(st.session_state['candidate_terraform_template']['output'], language="json")
      # creating a button to deploy the template
      st.session_state['code_exp'].button('Deploy template', key='deploy_button', type='primary')
    else:
      add_status_message("Candidate template not correct after validation.", 'error')
      code_expander_label = "red:[Generated Template WITH ERRORS]"
      st.session_state['code_exp'].error(st.session_state['tf_validation']['errors'], icon="🚨")
      # showing the incorrect template template
      st.session_state['code_exp'].code(st.session_state['candidate_terraform_template']['output'], language="json")
      code_expander_expanded = False
      # adding (not replacing) errors to be resolved
      st.session_state['previous_error'] = st.session_state.get('previous_error', '') \
        + '\nSolve the following error made when generating the previous template: ' \
        + ". ".join(st.session_state['tf_validation']['errors'])
      add_status_message(f"Retrying generation... {st.session_state['validate_retry_number']}/{MAX_RETRIES}", 'info')
      del st.session_state['candidate_terraform_template']
      # restoring correct main.tf to be sure all terraform commands works
      shutil.copyfile('main.tf.bk', 'main.tf')



def deploy_template():
  """Deploying the template."""
  # calling the agent to deploy the template
  st.session_state['terraform_template_deploy'] = st.session_state['tf_validation_agent'].invoke(
    {'user_message': [HumanMessage(
      content='Deploy the already created Terraform template')]},
      config=st.session_state['cfg'])

  # as the output returned is a json let's format it
  tmp_output = (st.session_state['terraform_template_deploy']['output']).replace("\n", "").replace("False", "false")
  tf_deploy_result = json.loads(tmp_output)
  # keeping the state for the widgets
  st.session_state['code_exp'] = state_cont.expander('Generated Template', expanded=True)
  if tf_deploy_result['valid'] is True:
    # showing suggestions if available
    add_status_message("Terraform apply executed Ok.", 'success')
    st.session_state['code_exp'].success("Template is being deployed. Please check status on cloud. ", icon="✅")
  else:
    add_status_message("Error deploying template (errors above template).", 'error')
    tmp_error = 'Error deploying template: ' + '. '.join(tf_deploy_result['errors'])
    st.session_state['code_exp'].error(tmp_error, icon="🚨")
    tmp_suggestions = 'Suggestions to solve the deployment errors: ' + '. '.join(tf_deploy_result['suggestions'])
    st.session_state['code_exp'].info(tmp_suggestions, icon="ℹ️")

  # showing the validate template
  st.session_state['code_exp'].code(st.session_state['candidate_terraform_template']['output'], language="json")
  # creating a button to deploy the template
  st.session_state['code_exp'].button('Deploy template', key='deploy_button', type='primary')


def submit_on_change():
  """Control app state before calling generate_template."""
  if 'candidate_terraform_template' in st.session_state:
    # deleting the previously generated candidate template
    del st.session_state['candidate_terraform_template']
  if 'tf_validation' in st.session_state:
    # the validation
    del st.session_state['tf_validation']
  if 'terraform_template' in st.session_state:
    # and the validated template
    del st.session_state['terraform_template']


def keeping_state_messages():
  """Keeping the app state showing widgets"""
  # restoring status info tab
  for m_text, m_type in st.session_state['history_status_message']:
    add_status_message(m_text, m_type, save=False)


def keeping_state_image():
  """Keeping the state for the image and description"""
  st.session_state['img_exp'] = image_cont.expander(label='Image uploaded.', expanded=True)
  st.session_state['img_exp'].image(uploaded_file, caption= "Content Image", use_column_width = True)
  st.session_state['img_exp'].success(st.session_state['solution_description'], icon="✅")


def keeping_state_submit_button():
  """."""
  if uploaded_file or user_input != '':
    st.session_state['submit_button_disabled'] = False
  else:
    st.session_state['submit_button_disabled'] = True


def new_agent_on_change_settings():
  """Forcing to create new agents if some settings are modified"""
  # whenever a setting is changed a new agent should be created
  if 'tf_developer_agent' in st.session_state:
    del st.session_state['tf_developer_agent']


#########################
#########################
# setting wide mode
st.set_page_config(layout="wide")
# starting streamlit app
st.title("NL2IaC")
# logging into langsmith
client = Client()

# initializing message history
if 'history_status_message' not in st.session_state:
  st.session_state['history_status_message'] = []

# creating a side bar for config purposes
with st.sidebar:
  st.markdown("<h1 style='text-align: center;'>Settings</h1>", unsafe_allow_html=True)
  st.radio("Choose provider to use:", ['OpenAI', 'Google'], horizontal=True,
           key='provider_id', on_change=new_agent_on_change_settings)
  if st.session_state.provider_id.lower() == 'openai':
    st.text_input("Model Id: ", value=OPENAI_MODEL_ID,
                  key='model_id', on_change=new_agent_on_change_settings)
    st.slider(label='Temperature', key='temperature',
              min_value=0.0, max_value=1.0, step=0.1,
              value=TEMPERATURE, on_change=new_agent_on_change_settings)
    st.text_input("API KEY: ",
                  value=st.secrets["OPENAI_API_KEY"],
                  type="password", key='api_key')
  else:
    st.text_input("Model Id: ", value=GOOGLE_MODEL_ID,
                  key='model_id', on_change=new_agent_on_change_settings)
    st.slider(label='Temperature', key='temperature',
              min_value=0.0, max_value=2.0, step=0.1,
              value=TEMPERATURE, on_change=new_agent_on_change_settings)
    st.text_input("Project ID: ", value=PROJECT_ID, key='project_id')
    st.text_input("Region: ", value=REGION, key='region_id')


# updating the OPENAI API KEY environment variable if updated
if st.session_state.provider_id.lower() == 'openai':
  os.environ["OPENAI_API_KEY"] = st.session_state.api_key

# creating terraform agents
if "tf_developer_agent" not in st.session_state:
  st.session_state['tf_developer_agent'] = nl2iac_agent.terraform_developer_agent(
    provider_id=st.session_state.provider_id, model_id=st.session_state.model_id,
    temperature=st.session_state.temperature)
  st.session_state['tf_validation_agent'] = nl2iac_agent.terraform_validator_agent(
    provider_id=st.session_state.provider_id, model_id=st.session_state.model_id,
    temperature=st.session_state.temperature)

# layout of the app
main_col, info_col = st.columns([0.7, 0.3], gap='medium')
with main_col:
  user_input = st.text_area('Enter an architecture description:')

  file_col, buttons_col = st.columns([0.7, 0.3], gap='medium')
  with file_col:
    uploaded_file = st.file_uploader("Or upload a solution design image", accept_multiple_files=False,
                                      label_visibility="visible", type=['png', 'jpg', 'jpeg'])
  state_cont = st.container()
  template_cont = st.empty()
  image_cont = st.container()

with info_col:
  status_tab, detailed_tab = st.tabs(["Status Info", "Detailed steps"])
  with detailed_tab:
    detailed_tab_cont = st.container()
  with status_tab:
    status_tab_cont = st.container(height=1000)

# creating callback for the agents if not already created
if 'st_callback' not in st.session_state:
  st_callback = StreamlitCallbackHandler(detailed_tab_cont)
  st.session_state['cfg'] = RunnableConfig()
  st.session_state['cfg']['callbacks'] = [st_callback]

# restoring status:
keeping_state_messages()

# app operations start
# when a file has been uploaded
if uploaded_file is not None:
  upload_image_and_generate_description()
  # keeping the state
  keeping_state_image()

# managing if the submit button should be enabled or disabled
keeping_state_submit_button()
# painting the submit button after check to enable or disable it
with buttons_col:
  submit_button = st.button('Generate template', on_click=submit_on_change,
                            use_container_width=True, type="primary",
                            disabled=st.session_state.get('submit_button_disabled', True))
  deploy_cont = st.empty()

# if generate template button has been clicked
EXIT_SUBMIT = False
if submit_button:
  while (not st.session_state.get('tf_validation_valid', False)) and (not EXIT_SUBMIT):
    st.session_state['validate_retry_number'] = st.session_state.get('validate_retry_number', 0) + 1
    generate_template()
    validate_template()
    if st.session_state.get('validate_retry_number', 0) >= MAX_RETRIES:
      add_status_message(f"Template coudn't be validated after {MAX_RETRIES} retries.", 'error')
      EXIT_SUBMIT = True

  # resetting previous errors and restoring variables
  EXIT_SUBMIT = False
  if 'previous_error' in st.session_state:
    del st.session_state['previous_error']
  if 'validate_retry_number' in st.session_state:
    del st.session_state['validate_retry_number']
  if 'tf_validation_valid' in st.session_state:
    del st.session_state['tf_validation_valid']

if ('deploy_button' in st.session_state) and (st.session_state.deploy_button):
  deploy_template()
