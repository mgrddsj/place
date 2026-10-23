# Place v3

Please see `architecture.png` for the architecture diagram of this version.

Deployed version is available at: https://place.jessexu.me

## File Structure
- `static_files/` - Frontend static files (HTML, CSS, JS)
- `lambda_functions/` - Backend Lambda function code
   - `webSocketV1/` - Main WebSocket handler Lambda
   - `placeBroadcaster/` - Lambda for broadcasting messages to clients
   - `ziao-sqs-logger/` - Lambda for logging draw events from SQS
   - `savePlacePNG/` - Lambda for generating the PNG image from SQS events

## AWS Services Used
- S3: Static file hosting for frontend, storing the place.png image.
- CloudFront: CDN for frontend static files.
- API Gateway: WebSocket API for real-time communication.
- Lambda: Serverless functions for backend logic.
- ElastiCache (Valkey): In-memory data store for client connections and drawing history.
- SQS: Message queues for decoupling draw event processing and PNG generation.
- VPC: Isolated network for Lambdas accessing ElastiCache.
- IAM: Manage roles and permissions for Lambda functions and creating IAM users for group members to access AWS console.
- CloudWatch: Logging and monitoring for Lambda functions.
- ACM: SSL certificates for custom domain.

## How we setup the project

### Static Frontend Hosting with S3 + CloudFront

1. Go to AWS S3 console and create a new S3 bucket. Leave "Block all public access" on. Keep other settings as default.
2. Go to CloudFront console - Distributions, create a new distribution. 
   - Use "Amazon S3" as origin type, select the S3 bucket created in step 1.
   - Check "Allow private S3 bucket access to CloudFront" and use recommended origin and cache settings.
   - Do not enable security protections for now (it's so EXPENSIVE).
3. Under distribution settings, set "Default root object" to `index.html`.
4. (Optional, but cool) Set up a custom domain because I have one. 
   - Click "Add domain" under "Alternate domain names" in the distribution settings.
   - Enter the domain, then click "Create certificate in ACM". 
      - In the ACM console, request a public certificate for the domain. Use DNS validation.
      - Add the DNS validation records in domain registrar's DNS settings (I use Cloudflare).
      - After the certificate is issued, go back to CloudFront distribution settings, select the certificate.
   - Add the domain.
   - In domain registrar's DNS settings, add a CNAME record pointing to the CloudFront distribution domain.

### Set up Backend with API Gateway, Lambda, ElastiCache, SQS

### Set up VPC
1. Create a VPC for the Lambdas that need to access ElastiCache (Valkey).
2. Create a security group allowing inbound/outbound traffic from 0.0.0.0/0 (on all ports) to all ports for simplicity.

### Set up VPC Endpoints

Lambdas inside VPC can't access AWS services directly - it needs VPC endpoints for each service. Make sure to select the correct service name, otherwise it won't work.

Note: API Gateway endpoint is an exception. If "private DNS" is enabled, its hostname will clash with the public API Gateway endpoint, causing resolution issues. If we disable private DNS for the API Gateway endpoint, the Lambda inside VPC won't be able to reach the API Gateway endpoint without a costly NAT gateway. (Reference: [link](https://repost.aws/knowledge-center/api-gateway-vpc-connections)) So we worked around this by "outsourcing" the broadcasting functionality to another Lambda outside the VPC. 

Endpoints we created:
- `api-gateway-endpoint` - service: `com.amazonaws.us-east-2.execute-api`
- `sts-endpoint` - for IAM authentication to ElastiCache
- `lambda-invoke-endpoint` - service: `com.amazonaws.us-east-2.lambda` - for invoking other Lambdas
- `sqs_endpoint` - service: `com.amazonaws.us-east-2.sqs` - for sending to SQS

### Set up ElastiCache (Valkey/Redis)
1. Create serverless Valkey cache on ElastiCache (`placev2valkey`) with default settings.
2. Create a user `place-v3` under "ElastiCache - Users" with access string `on ~* +@all` to connect to the cache.

### Set up SQS Queues
Create two SQS queues:

1. `ZiaoSQS` - standard queue for logging draw events.
2. `placePNG.fifo` - FIFO queue for PNG generation. Enable "High throughput FIFO queue".

Use default settings for other options.

### Set up API Gateway WebSocket API
1. Create a new WebSocket API named `placeV3` with route selection expression `$request.body.action`.
2. Create the following routes:
   - `$connect`
   - `$disconnect`
   - `draw`
   - `getHistory`
   - `checkRateLimit`
3. For each route, create an integration with the Lambda function `webSocketV1`. Also enable "Use Lambda Proxy integration" and "Two-way communication" for each route.

### Create Lambda Function (webSocketV1)

This is the main Lambda that handles all WebSocket routes. Python 3.13 with `redis`, `cachetools`, and `requests` packaged with the code. Lives inside the VPC so it can access ElastiCache.

Triggered by API Gateway WebSocket (placeV2) with these routes:
- `$connect` / `$disconnect` - manage client connections in Redis.
- `draw` - rate-limited (30s cooldown), stores to Redis, sends to SQS, invokes `placeBroadcaster` to broadcast updates.
- `getHistory` - fetches drawing history from Redis and loop send to one client with `placeBroadcaster` (used in v2, not in v3 anymore).
- `checkRateLimit` - returns cooldown status.

Notes:

In `draw`, it sends events to two SQS queues: `ZiaoSQS` (logging) and `placePNG.fifo` (PNG generation).

We originally tried broadcasting directly from this Lambda to API Gateway, but kept getting 403 errors. Turns out Lambdas inside VPC can't reach API Gateway endpoints directly. So we created `placeBroadcaster` outside VPC to handle broadcasts instead.

Steps to create:
1. Create function with Python 3.13, connect to the VPC with all subnets.
2. Set security group to allow all inbound/outbound (0.0.0.0/0).
3. Upload code with dependencies packaged.
4. Add IAM policies to role: `AmazonElastiCacheFullAccess`, `AmazonSQSFullAccess`, `AWSLambdaExecute`, `AWSLambdaVPCAccessExecutionRole`, plus inline policies for `execute-api:ManageConnections` and `lambda:InvokeFunction`.

### Create Lambda Function (placeBroadcaster)

Broadcasts messages to connected WebSocket clients. Python 3.13, no external libraries. Lives outside VPC. Gets invoked async by `webSocketV1`.

Takes a list of client IDs and uses API Gateway Management API to send messages to each. Handles stale connections gracefully.

1. Create function with Python 3.13, do not connect to VPC.
2. Add IAM policy in the role of this lambda function for `execute-api:ManageConnections`. (`AmazonAPIGatewayInvokeFullAccess` Managed policy can be used here.)
3. Upload code.

### Create Lambda Function (ziao-sqs-logger)

Consumes drawing events from SQS and logs them to CloudWatch. Python 3.13, no external libraries. Lives outside VPC. Triggered by `ZiaoSQS` queue.

Logs each draw event with timestamp, connection ID, and drawing data.

1. Create function with Python 3.13, no VPC.
2. Add SQS trigger for `ZiaoSQS`.
3. Add IAM policy: `AmazonSQSFullAccess`.

### Create Lambda Function (savePlacePNG)

Generates the PNG image from drawing events. Python 3.13 with `pypng` packaged. Lives outside VPC. Triggered by `placePNG.fifo` queue.

Reads pixel updates from SQS, fetches current image from S3 (`place-v3/place.png`), applies the changes, and saves back to S3. Creates a new 250x250 white image if none exists.

1. Create function with Python 3.13, no VPC.
2. Set security group to allow all inbound/outbound (0.0.0.0/0).
3. Add SQS trigger for `placePNG.fifo`.
4. Add IAM policies to role: `AmazonS3FullAccess`, `AmazonSQSFullAccess`, `AWSLambdaVPCAccessExecutionRole`.
5. Upload code with dependencies packaged.

### Resources consulted and references
Some resources we consulted while building this project:

- https://tutorialsdojo.com/using-origin-access-control-to-secure-s3-object-access-to-cloudfront/
- https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/LambdaRedis.html
- https://repost.aws/knowledge-center/api-gateway-vpc-connections
- https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/apigatewaymanagementapi/client/post_to_connection.html
- https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html 

## Provenance

This directory preserves the original AWS implementation (course project A3, group 68:
Jesse Xu, Ziao Liu, Leon Liang) exactly as submitted, for reference. The code under
`api/`, `gateway/` and the `worker` service in the repository root is the self-hosted
revival.

