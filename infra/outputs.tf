output "lambda_name" {
  value = aws_lambda_function.scout.function_name
}

output "topic_arn" {
  value = aws_sns_topic.leads.arn
}

output "table_name" {
  value = aws_dynamodb_table.seen.name
}
