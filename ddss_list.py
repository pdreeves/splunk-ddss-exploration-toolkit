import json, boto3, time, datetime, os, sys

# Splunk-related setup
BUCKET_NAME = os.environ["BUCKET_NAME"]
FIREHOSE_NAME = os.environ["FIREHOSE_NAME"]
SPLUNK_INDEX = os.environ["SPLUNK_INDEX"]

# AWS-related setup
AWS_LAMBDA_FUNCTION_NAME = os.environ["AWS_LAMBDA_FUNCTION_NAME"]
s3 = boto3.resource('s3')
firehoseClient = boto3.client('firehose', region_name=os.environ['AWS_REGION'])
recordBatch = []

# Retrieve all Splunk raw data files from the S3 bucket
def retrieveDDSSObjectList(bucketName):

    ddssBucket = s3.Bucket(BUCKET_NAME)
    objectList = []

    try:
        # Retrieve all objects, and just filter for ones ending in journal.zst which indicates them as a file containing raw indexed data
        for object in ddssBucket.objects.all():
            if (object.key[-11:] == "journal.zst"):
                objectList.append(str(object.key))

        return objectList

    except:
        raise TypeError("Unable to retrieve objects from S3 bucket:"  + BUCKET_NAME)

# Parse Splunk bucket events
def getBucketInfo(ddssObject):

    returnDict = {}

    # Split event
    ddssObjectSplit = ddssObject.split("/")
    ddssBucketSplit = ddssObjectSplit[-3].split("_")

    # Set earliest event timestamps in bucket
    returnDict["splunkBucketEarliestTimestampEpoch"] = ddssBucketSplit[2]
    returnDict["splunkBucketEarliestTimestamp"] = datetime.datetime.fromtimestamp(int(ddssBucketSplit[2])).isoformat()

    # Set latest event timestamps in bucket
    returnDict["splunkBucketLatestTimestampEpoch"] = ddssBucketSplit[1]
    returnDict["splunkBucketLatestTimestamp"] = datetime.datetime.fromtimestamp(int(ddssBucketSplit[1])).isoformat()

    # Set index
    returnDict["splunkBucketIndex"] = ddssObjectSplit[-4]

    # Set full bucket path
    returnDict["splunkBucketPath"] = ddssObject[:-20]

    # Set S3 bucket name
    returnDict["s3BucketName"] = BUCKET_NAME

    return returnDict

# Buffer and send events to Firehose
def sendEventsToFirehose(event, final):

    # Add current event ot recordBatch
    if (len(event) > 0): # This will be 0 if it's a final call to clear the buffer
        recordBatch.append({"Data": event})

    try:

        # If there are more than 200 records or 2MB in the sending queue, send the event to Splunk and clear the queue
        if (len(recordBatch) > 200 or (sys.getsizeof(recordBatch) > 2000000 )):
            firehoseClient.put_record_batch(DeliveryStreamName=FIREHOSE_NAME, Records=recordBatch)
            recordBatch.clear()
        elif (final == True):
            firehoseClient.put_record_batch(DeliveryStreamName=FIREHOSE_NAME, Records=recordBatch)
            recordBatch.clear()

    except:
        raise TypeError("Unable to send file to Firehose"  + FIREHOSE_NAME)

# Main handler
def handler(event, context):

    ddssObjects = retrieveDDSSObjectList(BUCKET_NAME)
    currentTime = time.time()

    for ddssObject in ddssObjects:

        # Get event data
        eventData = getBucketInfo(ddssObject)

        # Construct Splunk event
        splunkEvent = '{ "time": ' +  str(currentTime) + ', "host":"' + AWS_LAMBDA_FUNCTION_NAME + '", "source": "' + AWS_LAMBDA_FUNCTION_NAME + '", "sourcetype": "splunk-ddss-exploration-toolkit", "index": "' + SPLUNK_INDEX + '", "event":  ' + json.dumps(eventData) + ' }'

        # Send to Firehose
        sendEventsToFirehose(splunkEvent, False)

    # Send any remaining events to Firehose
    sendEventsToFirehose(splunkEvent, True)