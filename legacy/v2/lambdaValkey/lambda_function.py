import json
import redis 

# Using: https://redis.io/docs/latest/develop/clients/redis-py/
# Using:  https://redis.io/docs/latest/develop/clients/redis-py/connect/#connect-to-your-production-redis-with-tls
# Had to be on the same VPC (Simplest to create the lambda on the VPC, but you can figure this out)
# Had to use ssl=True

r = redis.Redis(host='############.serverless.use1.cache.amazonaws.com', port=6379, decode_responses=True, ssl=True)

def lambda_handler(event, context):
    # TODO implement
    v=r.incr("visits")
    print("v={}".format(v))
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

