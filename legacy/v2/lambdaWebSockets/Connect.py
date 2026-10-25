import json

def lambda_handler(event, context):
    print(event)
    print(event["requestContext"]["connectionId"])
    print("****")
    print(context)
    return { "statusCode" : 200 }
