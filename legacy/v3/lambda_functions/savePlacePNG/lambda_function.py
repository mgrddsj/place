import json
import boto3
from botocore.config import Config
from botocore.exceptions import ConnectTimeoutError, ReadTimeoutError
import png
from io import BytesIO

S3_BUCKET = 'place-v3'  
S3_KEY = 'place.png'
IMAGE_SIZE = 250

# Add timeout configuration
s3_config = Config(
    connect_timeout=3,
    read_timeout=3,
    retries={'max_attempts': 0}
)
s3_client = boto3.client('s3', config=s3_config)

def lambda_handler(event, context):
    print("Lambda function started")
    print(f"Remaining time: {context.get_remaining_time_in_millis()}ms")
    print(f"Processing {len(event.get('Records', []))} messages")
    
    # Collect all valid pixel updates from the batch
    pixel_updates = []
    for record in event.get('Records', []):
        try:
            message = json.loads(record['body'])
            if message.get('drawing_data', {}).get('action') != 'draw':
                continue
            data = message['drawing_data']
            x, y = int(data['x']), int(data['y'])
            r, g, b = int(data['r']), int(data['g']), int(data['b'])
            if 0 <= x < IMAGE_SIZE and 0 <= y < IMAGE_SIZE and all(0 <= c <= 255 for c in [r, g, b]):
                pixel_updates.append((x, y, r, g, b))
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            print(f"Skipping invalid message: {e}")
            continue
    
    if not pixel_updates:
        print("No valid pixel updates")
        return {'statusCode': 200, 'body': 'No valid updates'}
    
    print(f"Processing {len(pixel_updates)} pixel updates")
    
    # Try to get existing image from S3, or create new one
    pixels = None
    try:
        print(f"Fetching image from S3: {S3_BUCKET}/{S3_KEY}")
        print(f"Time before S3 call: {context.get_remaining_time_in_millis()}ms")
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
        print("S3 get_object succeeded")
        image_data = response['Body'].read()
        print(f"Read {len(image_data)} bytes")
        reader = png.Reader(bytes=image_data)
        width, height, rows, metadata = reader.read()
        pixels = [list(row) for row in rows]
        print(f"Loaded existing image: {width}x{height}")
    except (ConnectTimeoutError, ReadTimeoutError) as e:
        print(f"TIMEOUT connecting to S3 - likely VPC issue: {e}")
        pixels = [[255] * (IMAGE_SIZE * 3) for _ in range(IMAGE_SIZE)]
    except s3_client.exceptions.NoSuchKey:
        print("No existing image found, creating new white image")
        pixels = [[255] * (IMAGE_SIZE * 3) for _ in range(IMAGE_SIZE)]
    except Exception as e:
        print(f"Error loading image from S3: {type(e).__name__}: {str(e)}")
        pixels = [[255] * (IMAGE_SIZE * 3) for _ in range(IMAGE_SIZE)]

    # Apply all pixel updates
    for x, y, r, g, b in pixel_updates:
        pixel_index = x * 3
        pixels[y][pixel_index] = r
        pixels[y][pixel_index + 1] = g
        pixels[y][pixel_index + 2] = b
    print(f"Applied {len(pixel_updates)} pixel updates")

    # Save image back to S3
    print(f"Saving image to S3. Time remaining: {context.get_remaining_time_in_millis()}ms")
    buffer = BytesIO()
    writer = png.Writer(width=IMAGE_SIZE, height=IMAGE_SIZE, greyscale=False, alpha=False)
    writer.write(buffer, pixels)
    buffer.seek(0)
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY,
        Body=buffer,
        ContentType='image/png'
    )
    print("Image saved successfully")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Processed {} pixel updates'.format(len(pixel_updates)))
    }