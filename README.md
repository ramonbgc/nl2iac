# nl2iac
AI agent for IaC deployments

## installation
1. It's recommended to create and use a python virtual environment (not mandatory):
```sh
virtualenv YourOwnEnvName
cd YourOwnEnvName
source bin/activate
```

2. download/clone the repo 
3. install requirements:
```sh
pip install -r requirements.txt
```
4. add the following lines and fill the values in **.streamlit/secrets.toml**:

```sh
GOOGLE_APPLICATION_CREDENTIALS = "PathToYourServiceAccountJSONFile"
LANGCHAIN_API_KEY = "YourLangChainApiKey"
LANGCHAIN_PROJECT = "YourLangChainProjectName"
OPENAI_API_KEY = "YourOpenAIApiKey"
PROJECT_ID = "YourGCPProjectId"
```