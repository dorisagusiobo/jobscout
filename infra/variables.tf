variable "region" {
  type    = string
  default = "us-east-1"
}

variable "alert_email" {
  type        = string
  description = "Where lead digests and budget warnings go."
}

variable "schedule" {
  type        = string
  description = "EventBridge Scheduler expression, in America/New_York time."
  default     = "cron(0 8 ? * MON-FRI *)" # 8 AM on weekdays
}

variable "model" {
  type    = string
  default = "global.anthropic.claude-sonnet-4-6" # switch to anthropic.claude-opus-5-5 once access opens
}

variable "effort" {
  type    = string
  default = "low"
}

variable "min_score" {
  type    = number
  default = 70
}

variable "max_scores_per_run" {
  type        = number
  description = "Cap on Claude calls per run; extra postings wait for the next run."
  default     = 15
}

variable "monthly_budget_usd" {
  type    = number
  default = 10
}
