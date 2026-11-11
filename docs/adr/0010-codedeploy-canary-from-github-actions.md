# Deploy with GitHub Actions and CodeDeploy canaries, not CodePipeline

GitHub Actions authenticates to AWS through OIDC (no stored keys) and runs `cdk deploy`. Each Lambda publishes a new version behind an alias, and CodeDeploy shifts 10% of traffic for five minutes, rolling back automatically if error-rate or latency alarms fire. CodePipeline would duplicate the orchestration GitHub Actions already provides.
