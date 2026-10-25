import json
import boto3
import redis
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError
import os
import uuid
from typing import Tuple, Union
from urllib.parse import ParseResult, urlencode, urlunparse
import botocore.session
from botocore.model import ServiceId
from botocore.signers import RequestSigner
from cachetools import TTLCache
from datetime import datetime, timezone

# SQS Configuration
SQS_LOG_QUEUE_URL = 'https://sqs.us-east-2.amazonaws.com/912390896707/ZiaoSQS'
SQS_PNG_QUEUE_URL = 'https://sqs.us-east-2.amazonaws.com/912390896707/placePNG.fifo'

# API Gateway Configuration
APIGW_ENDPOINT_URL = 'https://0g7tn9o5f4.execute-api.us-east-2.amazonaws.com/production'

# Redis Configuration
# Endpoint provided in the prompt
REDIS_HOST = 'placev2valkey-rzwluh.serverless.use2.cache.amazonaws.com'
REDIS_PORT = 6379

# Rate Limiting Configuration
RATE_LIMIT_SECONDS = 30  # Cooldown time in seconds
RATE_LIMIT_WHITELIST = set([
    "client_jesse",
    "client_leon",
    "client_gary",
])

# IAM Auth Configuration
username = 'place-v3'
cache_name = 'placev2valkey'

class ElastiCacheIAMProvider(redis.CredentialProvider):
    def __init__(self, user, cache_name, is_serverless=False, region="us-east-2"):
        self.user = user
        self.cache_name = cache_name
        self.is_serverless = is_serverless
        self.region = region
        self._cache = TTLCache(maxsize=128, ttl=900)

    def _get_request_signer(self):
        """Create a fresh RequestSigner to avoid weakly-referenced object issues."""
        session = botocore.session.get_session()
        return RequestSigner(
            ServiceId("elasticache"),
            self.region,
            "elasticache",
            "v4",
            session.get_credentials(),
            session.get_component("event_emitter"),
        )

    # Generated IAM tokens are valid for 15 minutes
    def get_credentials(self) -> Union[Tuple[str], Tuple[str, str]]:
        # Check cache first
        cache_key = (self.user, self.cache_name, self.is_serverless, self.region)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        query_params = {"Action": "connect", "User": self.user}
        if self.is_serverless:
            query_params["ResourceType"] = "ServerlessCache"
        url = urlunparse(
            ParseResult(
                scheme="https",
                netloc=self.cache_name,
                path="/",
                query=urlencode(query_params),
                params="",
                fragment="",
            )
        )
        # Create a fresh RequestSigner each time to avoid weak reference issues
        request_signer = self._get_request_signer()
        signed_url = request_signer.generate_presigned_url(
            {"method": "GET", "url": url, "body": {}, "headers": {}, "context": {}},
            operation_name="connect",
            expires_in=900,
            region_name=self.region,
        )
        # RequestSigner only seems to work if the URL has a protocol, but
        # Elasticache only accepts the URL without a protocol
        # So strip it off the signed URL before returning
        result = (self.user, signed_url.removeprefix("https://"))
        self._cache[cache_key] = result
        return result

# Initialize Credential Provider
creds_provider = ElastiCacheIAMProvider(user=username, cache_name=cache_name, is_serverless=True, region="us-east-2")

# Configure retry strategy for connection resilience in Lambda
retry = Retry(ExponentialBackoff(), 3, supported_errors=(ConnectionError, TimeoutError, BusyLoadingError))

# ElastiCache Serverless requires SSL
# Added socket_connect_timeout to fail fast if network is unreachable
# Added health_check_interval to detect stale connections
# Added retry for automatic reconnection on transient failures
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    ssl=True,
    ssl_cert_reqs="none",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    credential_provider=creds_provider,
    retry=retry,
    retry_on_timeout=True,
    health_check_interval=5,  # Check connection health every 5 seconds
)

def lambda_handler(event, context):
    # Log the incoming event for debugging purposes
    print("Received event:", json.dumps(event))

    # Extract request context details
    request_context = event.get('requestContext', {})
    route_key = request_context.get('routeKey')
    connection_id = request_context.get('connectionId')
    domain_name = request_context.get('domainName')
    stage = request_context.get('stage')

    print(f"Route Key: {route_key}, Connection ID: {connection_id}, Domain Name: {domain_name}, Stage: {stage}")

    # Initialize API Gateway Management API client
    if domain_name and stage:
        # endpoint_url = f"https://{domain_name}/{stage}"
        endpoint_url = APIGW_ENDPOINT_URL
        apigw_management = boto3.client('apigatewaymanagementapi', 
                                        endpoint_url=endpoint_url,
                                        config=boto3.session.Config(inject_host_prefix=False))
        
        def set_host_header(request, **kwargs):
            # Delete existing Host header if present, then add the correct one
            if 'Host' in request.headers:
                del request.headers['Host']
            request.headers['Host'] = domain_name
        
        apigw_management.meta.events.register('before-sign.apigatewaymanagementapi.*', set_host_header)
    else:
        apigw_management = None

    # Route handling
    if route_key == '$connect':
        return handle_connect(connection_id, apigw_management)
    elif route_key == 'getHistory':
        return handle_get_history(connection_id, apigw_management)
    elif route_key == '$disconnect':
        return handle_disconnect(connection_id)
    elif route_key == 'draw':
        body = event.get('body', '')
        return handle_draw(connection_id, body, apigw_management)
    elif route_key == 'checkRateLimit':
        body = event.get('body', '')
        return handle_check_rate_limit(connection_id, body, apigw_management)
    else:
        return {'statusCode': 400, 'body': f'Unknown route: {route_key}'}

def handle_connect(connection_id, apigw_management):
    print(f"Handling connect for {connection_id}")
    try:
        # Add new client to the list of connected clients in Redis
        r.sadd('connected_clients', connection_id)
        print("Added client to Redis")
    except redis.exceptions.RedisError as e:
        print(f"Redis connection error: {e}")
        return {'statusCode': 500, 'body': 'Redis connection failed'}

    return {'statusCode': 200, 'body': 'Connected'}

def handle_get_history(connection_id, apigw_management):
    print(f"Handling getHistory for {connection_id}")
    try:
        # Consult Redis for history of all points
        history = r.lrange('drawing_history', 0, -1)
        print(f"Retrieved history of size {len(history)}")
        
        # Delegate sending history to external Lambda (outside VPC)
        if history:
            lambda_client = boto3.client('lambda')
            history_payload = {
                'clients': [connection_id],
                'history': history,
                'endpoint_url': APIGW_ENDPOINT_URL
            }
            try:
                lambda_client.invoke(
                    FunctionName='placeBroadcaster',
                    InvocationType='Event',
                    Payload=json.dumps(history_payload)
                )
                print(f"History send delegated for {len(history)} items to {connection_id}")
            except Exception as e:
                print(f"Error invoking broadcast Lambda for history: {e}")
        else:
            print("No history to send")
    except redis.exceptions.RedisError as e:
        print(f"Redis error during history retrieval: {e}")
    
    return {'statusCode': 200, 'body': 'History sent'}

def handle_disconnect(connection_id):
    print(f"Handling disconnect for {connection_id}")
    try:
        # Remove client from the list of connected clients in Redis
        r.srem('connected_clients', connection_id)
    except redis.exceptions.RedisError as e:
        print(f"Redis error during disconnect: {e}")
    return {'statusCode': 200, 'body': 'Disconnected'}

def handle_check_rate_limit(connection_id, body, apigw_management):
    """Handle rate limit status check for a client."""
    print(f"Handling checkRateLimit for {connection_id}")
    try:
        data = json.loads(body) if body else {}
        client_id = data.get('clientId')
        
        if not client_id:
            return {'statusCode': 400, 'body': 'Missing clientId'}
        
        # Check Redis for next available time
        rate_limit_key = f'rate_limit:{client_id}'
        next_available = r.get(rate_limit_key)
        
        response = {
            'type': 'rateLimit',
            'nextAvailableTime': int(float(next_available)) if next_available else 0
        }

        return {'statusCode': 200, 'body': json.dumps(response)}
        
    except redis.exceptions.RedisError as e:
        print(f"Redis error during rate limit check: {e}")
        return {'statusCode': 500, 'body': 'Redis error'}
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return {'statusCode': 400, 'body': 'Invalid JSON'}

def handle_draw(sender_connection_id, body, apigw_management):
    print(f"Handling message from {sender_connection_id}")
    try:
        # Parse the body to get clientId for rate limiting
        data = json.loads(body) if body else {}
        client_id = data.get('clientId')
        
        if not client_id:
            print("Missing clientId in draw request")
            return {'statusCode': 400, 'body': 'Missing clientId'}
        
        # Check rate limit
        rate_limit_key = f'rate_limit:{client_id}'
        current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        next_available = r.get(rate_limit_key)
        
        if client_id in RATE_LIMIT_WHITELIST:  # Whitelisted clients bypass rate limiting
            print(f"Client {client_id} is whitelisted, skipping rate limit")
            next_available = None
        elif next_available and current_time_ms < int(float(next_available)):
            # Client is rate limited
            print(f"Client {client_id} is rate limited until {next_available}")
            error_response = {
                'type': 'error',
                'error': 'rate_limited',
                'nextAvailableTime': int(float(next_available))
            }
            return {'statusCode': 429, 'body': json.dumps(error_response)}
        
        # Set new rate limit (current time + cooldown)
        new_next_available = current_time_ms + (RATE_LIMIT_SECONDS * 1000)
        r.set(rate_limit_key, str(new_next_available), ex=RATE_LIMIT_SECONDS + 60)  # TTL slightly longer than cooldown
        
        # Remove clientId from body before storing in history (not needed for broadcast)
        draw_data = {k: v for k, v in data.items() if k != 'clientId'}
        draw_body = json.dumps(draw_data)
        
        # Store the message in Redis history
        if draw_body:
            r.rpush('drawing_history', draw_body)
        
        # Ask Redis for the list of connected clients
        clients = r.smembers('connected_clients')
    except redis.exceptions.RedisError as e:
        print(f"Redis error during message handling: {e}")
        return {'statusCode': 500, 'body': 'Redis error'}
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return {'statusCode': 400, 'body': 'Invalid JSON'}
    
    # Write to fifo PNG SQS Queue for image generation
    try:
        if draw_body:
            sqs_client = boto3.client('sqs')
            png_message = {
                'connection_id': sender_connection_id,
                'drawing_data': draw_data,
                'timestamp_iso': datetime.now(timezone.utc).isoformat()
            }
            sqs_client.send_message(
                QueueUrl=SQS_PNG_QUEUE_URL,
                MessageBody=json.dumps(png_message),
                MessageGroupId='placePNGGroup',  # Required for FIFO queues
                MessageDeduplicationId=f"{sender_connection_id}-{datetime.now(timezone.utc).timestamp()}-{uuid.uuid4().hex[:8]}"
            )
            print(f"PNG generation message sent to SQS")
    except Exception as e:
        print(f"Error sending PNG generation message to SQS: {e}")
    
    # Invoke external Lambda (outside VPC) to handle broadcast to API Gateway
    if clients and draw_body:
        lambda_client = boto3.client('lambda')
        broadcast_payload = {
            'clients': list(clients),
            'body': draw_body,
            'endpoint_url': APIGW_ENDPOINT_URL
        }
        try:
            lambda_client.invoke(
                FunctionName='placeBroadcaster',
                InvocationType='Event',
                Payload=json.dumps(broadcast_payload)
            )
            print(f"Broadcast delegated for {len(clients)} clients")
        except Exception as e:
            print(f"Error invoking broadcast Lambda: {e}")
    
    # Send drawing event to SQS for logging
    if draw_body:
        try:
            sqs_client = boto3.client('sqs')
            log_message = {
                'connection_id': sender_connection_id,
                'client_id': client_id,
                'drawing_data': draw_data,
                'timestamp_iso': datetime.now(timezone.utc).isoformat()
            }
            sqs_client.send_message(
                QueueUrl=SQS_LOG_QUEUE_URL,
                MessageBody=json.dumps(log_message)
            )
            print(f"Drawing event sent to SQS")
        except Exception as e:
            print(f"Error sending to SQS: {e}")

    # Return the new rate limit info to the client (two-way communication)
    response = {
        'type': 'rateLimit',
        'nextAvailableTime': new_next_available
    }
    return {'statusCode': 200, 'body': json.dumps(response)}
