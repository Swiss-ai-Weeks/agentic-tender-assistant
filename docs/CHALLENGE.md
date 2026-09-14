# Agentic Tender Assistant

**Hackathon:** HPE & NVIDIA Agentic AI Hackathon for Enterprises — Swiss AI Weeks
**Difficulty:** Hard
**Suggested tools:** NVIDIA NeMo Agent Toolkit / NemoClaw
**Suggested data source:** [simap.ch](https://www.simap.ch/en) (Swiss public procurement platform)
**Repo:** https://github.com/Swiss-ai-Weeks/agentic-tender-assistant

## Overview

Build an agent that searches for public tenders, analyzes their requirements, and produces a
structured qualification briefing.

## Summary

Turn thousands of public tenders into actionable opportunities. Build an AI agent that can
investigate public tenders and help a user determine whether an opportunity is worth pursuing.
The assistant should go beyond summarization: it should understand requirements, connect
information across documents, and turn its research into a structured qualification briefing.

## Detailed Description

Build an agentic assistant that searches public tender opportunities, analyzes their
requirements, and produces a structured qualification briefing. The system should be able to:

- Identify relevant tenders
- Inspect their documentation
- Extract key requirements, deadlines, and eligibility criteria
- Summarize the opportunity in a format useful for a potential bidder

Participants can experiment with multiple agents, tool use, web or document retrieval, and
structured outputs.

## Suggested Technologies

- NVIDIA NeMo Agent Toolkit
- NemoClaw

## Suggested Data Source

- [simap.ch](https://www.simap.ch/en) — official Swiss public procurement platform
  (Confederation, cantons, and communes). No public API; legacy session-based (JSP) interface.
  Documents are published as tender notices + specification documents (cahier des charges) +
  annexes, often in FR/DE/IT depending on the canton.
