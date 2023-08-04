from pprint import pprint
import json
import os
import requests

def run_query(path, method="GET", payload=None):
  tfc_api_token = os.environ.get("TFC_API_TOKEN")

  headers = {
    "Authorization": f"Bearer {tfc_api_token}",
    "Content-Type": "application/vnd.api+json",
  }

  url = f"https://app.terraform.io/api/v2{path}"
  response = requests.request(method, url, json=payload, headers=headers)
  if response.status_code == 200:
    return response.json()
  else:
    print(response.json())
    raise Exception(f"Query to {path} failed with code of {response.status_code}")


def list_workspaces(organization_id):
  return run_query(f"/workspaces/{organization_id}/vars")

def loadConfigurationFromFile(path="config.json"):
  with open(path) as file:
    return json.load(file)

config = loadConfigurationFromFile()

result = list_workspaces(config["exporter"]["tfc"]["organization_id"])
pprint(result)
