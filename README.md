# Happie

This is my implementation of an MCP server for the Albert Heijn API. Use with
caution, I can't help you if they ban you from the API endpoints.

## Goal of this MCP Server

You can use this MCP server to give your [Hermes Agent](https://hermes-agent.nousresearch.com/)
or Claude the capability to find information about groceries and previous 
purchases at Albert Heijn. 

## System requirements

- [uv](https://astral.sh/uv)
- Linux with Gnome/KDE/COSMIC or any other XDG-compatible desktop environment.

I am not planning on supporting other environments like Windows and Mac. If you 
need support, feel free to submit a pull request.

## Getting started

- `git clone https://github.com/wmeints/happie`
- `cd happie`
- `uv install`
- `uv run happie auth login`
- `uv run happie serve`

## Documentation

- [Architecture documentation](docs/architecture)
