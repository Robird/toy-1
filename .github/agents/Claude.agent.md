---
name: Claude
description: 使用Claude模型的泛用Agent
model: Claude Sonnet 4.6 (copilot)
tools: [execute/getTerminalOutput, execute/killTerminal, execute/sendToTerminal, execute/runInTerminal, read/problems, read/readFile, read/viewImage, read/terminalSelection, read/terminalLastCommand, agent, edit/createDirectory, edit/createFile, edit/editFiles, edit/rename, search, web, ms-vscode.vscode-websearchforcopilot/websearch] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---