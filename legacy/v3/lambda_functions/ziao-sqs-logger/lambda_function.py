import json

def lambda_handler(event, context):
    print("=" * 50)
    print("DRAWING LOG - Chronological Order")
    print("=" * 50)
    
    for idx, record in enumerate(event.get('Records', []), 1):
        body = json.loads(record.get('body', '{}'))
        print(f"[{idx}] {body.get('timestamp_iso', 'N/A')}")
        print(f"    User: {body.get('connection_id', 'N/A')}")
        print(f"    Draw: {body.get('drawing_data', 'N/A')}")
        print()
    
    return {'statusCode': 200}