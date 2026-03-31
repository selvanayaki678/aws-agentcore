# Terraform configuration for AWS Bedrock Restaurant Reservation System
# This creates: DynamoDB table, Lambda function, IAM roles, and permissions

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================================================
# VARIABLES
# ============================================================================

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "restaurant-reservation"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 256
}

# ============================================================================
# DYNAMODB TABLE
# ============================================================================

resource "aws_dynamodb_table" "reservations" {
  name           = "${var.project_name}-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"  # On-demand pricing
  hash_key       = "reservationDate"
  range_key      = "confirmationNumber"

  attribute {
    name = "reservationDate"
    type = "S"  # String
  }

  attribute {
    name = "confirmationNumber"
    type = "S"  # String
  }

  # Optional: Add Global Secondary Index for querying by customer
  # Uncomment if you want to search reservations by customer name
  # attribute {
  #   name = "customerPhone"
  #   type = "S"
  # }
  
  # global_secondary_index {
  #   name            = "CustomerPhoneIndex"
  #   hash_key        = "customerPhone"
  #   projection_type = "ALL"
  # }

  # Enable point-in-time recovery for production
  point_in_time_recovery {
    enabled = var.environment == "prod" ? true : false
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  # Tags
  tags = {
    Name        = "${var.project_name}-table"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = var.project_name
  }
}

# ============================================================================
# IAM ROLE FOR LAMBDA
# ============================================================================

# Lambda execution role
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-lambda-role"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Policy for DynamoDB access
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "${var.project_name}-lambda-dynamodb-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.reservations.arn,
          "${aws_dynamodb_table.reservations.arn}/index/*"
        ]
      }
    ]
  })
}

# Attach AWS managed policy for Lambda basic execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ============================================================================
# LAMBDA FUNCTION
# ============================================================================

# Create ZIP file from Python code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

# Lambda function
resource "aws_lambda_function" "reservation_handler" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${var.project_name}-handler-${var.environment}"
  role            = aws_iam_role.lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = var.lambda_runtime
  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory

  environment {
    variables = {
      TABLE_NAME  = aws_dynamodb_table.reservations.name
      ENVIRONMENT = var.environment
    }
  }

  # Enable tracing for debugging
  tracing_config {
    mode = "Active"
  }

  tags = {
    Name        = "${var.project_name}-lambda"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.lambda_dynamodb_policy
  ]
}

# CloudWatch Log Group for Lambda (with retention)
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.reservation_handler.function_name}"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = {
    Name        = "${var.project_name}-lambda-logs"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ============================================================================
# LAMBDA PERMISSION FOR BEDROCK
# ============================================================================

# Resource-based policy to allow Bedrock to invoke Lambda
resource "aws_lambda_permission" "allow_bedrock" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reservation_handler.function_name
  principal     = "bedrock.amazonaws.com"
  
  # Optional: Restrict to specific agent (uncomment and set after agent creation)
  # source_arn    = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent/*"
}

# ============================================================================
# DATA SOURCES
# ============================================================================

data "aws_caller_identity" "current" {}

# ============================================================================
# OUTPUTS
# ============================================================================

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.reservations.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.reservations.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.reservation_handler.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.reservation_handler.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_role.arn
}

output "lambda_invoke_arn" {
  description = "Invoke ARN for the Lambda function"
  value       = aws_lambda_function.reservation_handler.invoke_arn
}

output "aws_region" {
  description = "AWS region where resources are deployed"
  value       = var.aws_region
}

output "setup_instructions" {
  description = "Next steps after Terraform deployment"
  value = <<-EOT
  
  ✅ Infrastructure deployed successfully!
  
  Next steps:
  
  1. Go to AWS Bedrock Console
  2. Create a new Agent with these settings:
     - Name: RestaurantAssistant
     - Model: Claude 3.5 Sonnet (or latest)
  
  3. Add Action Group:
     - Name: RestaurantActions
     - Lambda Function: ${aws_lambda_function.reservation_handler.function_name}
     - Upload API Schema: restaurant-api-schema.json
  
  4. Test your agent!
  
  Lambda Function ARN: ${aws_lambda_function.reservation_handler.arn}
  DynamoDB Table: ${aws_dynamodb_table.reservations.name}
  Region: ${var.aws_region}
  
  EOT
}
