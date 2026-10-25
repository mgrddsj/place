import json
import urllib3
import boto3

client = boto3.client('apigatewaymanagementapi', endpoint_url="https://XXXXXXXX.execute-api.us-east-1.amazonaws.com/production")

def lambda_handler(event, context):
    print(event)
    
    #Extract connectionId from incoming event
    connectionId = event["requestContext"]["connectionId"]
    
    #Do something interesting... 
    responseMessage = "responding..."+str(connectionId)
    
    # TODO: Well, in the example below you are posting back to the ont connectionId, for a broadcast
    # you need to get all of the connectionId and post back to all of them. So you need to store
    # them someplace, grab them here and loop through and speak to them all.

    #Form response and post back to connectionId
    response = client.post_to_connection(ConnectionId=connectionId, Data=json.dumps(responseMessage).encode('utf-8'))

    return { "statusCode": 200  }

