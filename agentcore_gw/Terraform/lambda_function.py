"""
Restaurant Reservation Lambda for AWS Bedrock AgentCore Gateway
Handles two tools: checkAvailability and bookTable
"""

import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME')


def lambda_handler(event, context):
    """
    AgentCore Gateway Lambda event is a FLAT dict of your inputSchema properties.
    
    e.g. for checkAvailability:
    {
        "date": "2026-03-15",
        "time": "19:00",
        "partySize": "4"
    }
    
    Tool name is in context object:
    context.client_context.custom['bedrockAgentCoreToolName'] = 'prefix_checkAvailability'
    """
    print(f"Received event: {json.dumps(event)}")

    # Resolve tool name from context (strip gateway-added prefix)
    tool_name = ""
    try:
        tool_name = context.client_context.custom.get('bedrockAgentCoreToolName', '')
        # Strip prefix (e.g., "gateway123_checkAvailability" -> "checkAvailability")
        if '___' in tool_name:
            tool_name = tool_name.split('___', 1)[-1]
    except Exception as e:
        print(f"Could not read tool name from context: {e}")

    print(f"Resolved tool name: {tool_name}")

    # Route based on tool name
    if tool_name == 'checkAvailability':
        result = check_availability(event)
    elif tool_name == 'bookTable':
        result = book_table(event)
    else:
        result = {'error': f'Unknown tool: {tool_name}'}

    print(f"Result: {json.dumps(result)}")
    return result  # AgentCore Gateway expects a plain JSON-serializable dict


def check_availability(params):
    """
    Expected params:
    - date: YYYY-MM-DD
    - time: HH:MM (24h)
    - partySize: integer (as string from gateway)
    """
    try:
        date = params.get('date')
        time = params.get('time')
        party_size = int(params.get('partySize', 2))

        if not date or not time:
            return {'error': 'Missing required parameters: date and time'}

        table = dynamodb.Table(TABLE_NAME)
        booked_tables = 0

        try:
            response = table.query(
                KeyConditionExpression='reservationDate = :date',
                FilterExpression='reservationTime = :time',
                ExpressionAttributeValues={
                    ':date': date,
                    ':time': time
                }
            )
            booked_tables = len(response.get('Items', []))
        except Exception as e:
            print(f"DynamoDB query error: {e}")

        available_tables = max(0, 5 - booked_tables)
        is_available = available_tables > 0

        return {
            'available': is_available,
            'date': date,
            'time': time,
            'partySize': party_size,
            'availableTables': available_tables,
            'message': f"{'Available' if is_available else 'Fully booked'} for {party_size} people on {date} at {time}"
        }

    except Exception as e:
        return {'error': f'Error checking availability: {str(e)}'}


def book_table(params):
    """
    Expected params:
    - date, time, partySize, customerName, customerPhone
    - specialRequests (optional)
    """
    try:
        date = params.get('date')
        time = params.get('time')
        party_size = int(params.get('partySize'))
        customer_name = params.get('customerName')
        customer_phone = params.get('customerPhone')
        special_requests = params.get('specialRequests', 'None')

        if not all([date, time, party_size, customer_name, customer_phone]):
            return {'error': 'Missing required parameters'}

        # Check availability first
        availability = check_availability({
            'date': date, 'time': time, 'partySize': party_size
        })

        if not availability.get('available'):
            return {
                'success': False,
                'message': f'No tables available on {date} at {time}',
                'availableTables': 0
            }

        confirmation_number = f"RES{datetime.now().strftime('%Y%m%d%H%M%S')}"

        try:
            table = dynamodb.Table(TABLE_NAME)
            table.put_item(Item={
                'reservationDate': date,
                'confirmationNumber': confirmation_number,
                'reservationTime': time,
                'partySize': party_size,
                'customerName': customer_name,
                'customerPhone': customer_phone,
                'specialRequests': special_requests,
                'createdAt': datetime.now().isoformat(),
                'status': 'confirmed'
            })
        except Exception as e:
            print(f"DynamoDB write error: {e}")

        return {
            'success': True,
            'confirmationNumber': confirmation_number,
            'date': date,
            'time': time,
            'partySize': party_size,
            'customerName': customer_name,
            'message': f'Reservation confirmed! Confirmation #: {confirmation_number}'
        }

    except Exception as e:
        return {'error': f'Error booking table: {str(e)}'}