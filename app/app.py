#!/usr/bin/env python3
"""
CDK entry point.

Deploy the entire backend in one command (from project root):
    cdk deploy "FeedbackApp/**" --profile backend-test

To diff without deploying:
    cdk diff  "FeedbackApp/**" --profile backend-test

All stacks, cross-stack wiring, and IAM grants live in FeedbackAppStage.
"""
import os
import sys

# Allow `from stacks.xxx` and `from stages.xxx` imports when CDK invokes
# this file as `python app/app.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aws_cdk as cdk
from stages.feedback_stage import FeedbackAppStage

app = cdk.App()
FeedbackAppStage(app, "FeedbackApp")
app.synth()
