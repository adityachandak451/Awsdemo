import sys
import os
import boto3
import pandas as pd
from io import BytesIO
from awsglue.utils import getResolvedOptions

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'inbound_path', 'outbound_path'])

def split_s3_path(s3_path):
    path_parts = s3_path.replace("s3://", "").split("/", 1)
    bucket = path_parts[0]
    key = ''
    if len(path_parts) > 1:
        key = path_parts[1]
    return bucket, key

def list_all_objects(bucket, prefix):
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)
    objects = []
    for page in page_iterator:
        if 'Contents' in page:
            objects.extend(page['Contents'])
    return objects

# Split inbound and outbound paths
in_bucket, in_prefix = split_s3_path(args['inbound_path'])
out_bucket, out_prefix = split_s3_path(args['outbound_path'])

# Ensure prefixes end with '/'
if in_prefix and not in_prefix.endswith('/'):
    in_prefix += '/'
if out_prefix and not out_prefix.endswith('/'):
    out_prefix += '/'

s3 = boto3.client('s3')
all_objects = list_all_objects(in_bucket, in_prefix)

for obj in all_objects:
    key = obj['Key']
    if key == in_prefix:
        continue  # Skip directory marker
    try:
        # Read file based on extension
        if not key.lower().endswith('.csv'):
            print(f"Skipping non-CSV file: {key}")
            continue
        
        # Read CSV into DataFrame
        response = s3.get_object(Bucket=in_bucket, Key=key)
        df = pd.read_csv(response['Body'])
        
        # Build output path
        relative_key = key[len(in_prefix):]
        if not relative_key:
            continue
        
        # Change extension to .parquet
        dir_name = os.path.dirname(relative_key)
        file_name = os.path.basename(relative_key)
        base_name, _ = os.path.splitext(file_name)
        new_file_name = f"{base_name}.parquet"
        output_relative = os.path.join(dir_name, new_file_name) if dir_name else new_file_name
        output_key = f"{out_prefix}{output_relative}"
        
        # Write DataFrame to Parquet
        parquet_buffer = BytesIO()
        df.to_parquet(parquet_buffer, engine='pyarrow', index=False)
        s3.put_object(Bucket=out_bucket, Key=output_key, Body=parquet_buffer.getvalue())
        print(f"Processed: {key} -> {output_key}")
    
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")