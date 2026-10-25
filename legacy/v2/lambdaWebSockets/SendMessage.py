import json
import urllib3
import boto3

client = boto3.client('apigatewaymanagementapi', endpoint_url="https://###########.execute-api.us-east-1.amazonaws.com/production")

def lambda_handler(event, context):
    print(event)
    
    #Extract connectionId from incoming event
    connectionId = event["requestContext"]["connectionId"]
    
    #Do something interesting... 
    body = json.loads(event["body"])
    responseMessage = body["message"]

    #Form response and post back to connectionId
    response = client.post_to_connection(ConnectionId=connectionId, Data=json.dumps(responseMessage).encode('utf-8'))

    return { "statusCode": 200  }

