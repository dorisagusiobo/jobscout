terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "jobscout" }
  }
}

locals {
  name = "jobscout"
}

# ---------- Memory: postings already scored ----------

resource "aws_dynamodb_table" "seen" {
  name         = "${local.name}-seen"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# ---------- Alerts ----------

resource "aws_sns_topic" "leads" {
  name = "${local.name}-leads"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.leads.arn
  protocol  = "email"
  endpoint  = var.alert_email # AWS emails a confirmation link; click it once
}

# ---------- Lambda ----------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
  statement {
    sid       = "Memory"
    actions   = ["dynamodb:BatchGetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.seen.arn]
  }
  statement {
    sid       = "Alerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.leads.arn]
  }
  statement {
    sid = "ClaudeOnBedrock"
    # Mantle (Messages API) for anthropic.* IDs; InvokeModel for global./us. inference profiles.
    actions   = ["bedrock-mantle:CreateInference", "bedrock:InvokeModel"]
    resources = ["*"] # narrow to the model ARN once it shows in your account
  }
}

resource "aws_iam_role_policy" "lambda" {
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "scout" {
  function_name    = local.name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "jobscout.handler.lambda_handler"
  filename         = "${path.module}/../build/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../build/lambda.zip")
  timeout          = 900
  memory_size      = 512

  environment {
    variables = {
      JOBSCOUT_TABLE      = aws_dynamodb_table.seen.name
      JOBSCOUT_TOPIC_ARN  = aws_sns_topic.leads.arn
      JOBSCOUT_MODEL      = var.model
      JOBSCOUT_EFFORT     = var.effort
      JOBSCOUT_MIN_SCORE  = tostring(var.min_score)
      JOBSCOUT_MAX_SCORES = tostring(var.max_scores_per_run)
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# ---------- Schedule ----------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.scout.arn
    }]
  })
}

resource "aws_scheduler_schedule" "scan" {
  name                         = "${local.name}-scan"
  schedule_expression          = var.schedule
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scout.arn
    role_arn = aws_iam_role.scheduler.arn
    retry_policy {
      maximum_retry_attempts = 0 # a missed run is picked up by the next one
    }
  }
}

# ---------- Cost guardrail (whole account, so Bedrock usage is included) ----------

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
