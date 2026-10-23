import json
import boto3

def lambda_handler(event, context):
    clients = event.get('clients', [])
    body = event.get('body', '')
    history = event.get('history', [])
    endpoint_url = event.get('endpoint_url')
    
    if not clients or not endpoint_url:
        print("Missing required parameters")
        return {'statusCode': 400, 'body': 'Missing parameters'}
    
    if not body and not history:
        print("No body or history to send")
        return {'statusCode': 400, 'body': 'No data to send'}
    
    # Initialize API Gateway Management API client
    apigw_management = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
    
    stale_connections = []
    sent_count = 0
    
    for client_id in clients:
        try:
            # If history is provided, send all history items
            if history:
                for item in history:
                    apigw_management.post_to_connection(ConnectionId=client_id, Data=item)
                    sent_count += 1
            # Otherwise send single body message
            elif body:
                apigw_management.post_to_connection(ConnectionId=client_id, Data=body)
                sent_count += 1
        except apigw_management.exceptions.GoneException:
            print(f"Connection {client_id} is gone")
            stale_connections.append(client_id)
        except Exception as e:
            print(f"Error sending to {client_id}: {e}")
    
    print(f"Sent {sent_count} messages. {len(stale_connections)} stale connections")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'sent': sent_count,
            'stale': stale_connections
        })
    }