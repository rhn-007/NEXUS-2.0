# NEXUS 2.0 — Personal AI Assistant

**A locally powered, voice-enabled personal AI assistant built with Python.**

NEXUS 2.0 is a personal AI assistant project designed to bring together conversational AI, voice interaction, memory, browser automation, and an extensible tool system in one application.

Inspired by the idea of a personal assistant like J.A.R.V.I.S., NEXUS is being developed to move beyond ordinary question-and-answer chat. The goal is to create an assistant that can understand requests, maintain useful context, interact through voice, and gradually gain the ability to carry out practical tasks.

The project uses **Ollama for local language-model inference**, Faster-Whisper for speech recognition, Piper for text-to-speech, and a modular Python architecture that separates the assistant's core logic from its AI, memory, voice, and tool components.

> **Project status:** Active development. Core conversational AI, voice components, response styling, memory components, browser-tool integration, and input-mode handling have been developed. Some advanced capabilities remain under development and may require further integration or testing.

**Repository:** [rhn-007/NEXUS-2.0](https://github.com/rhn-007/NEXUS-2.0)

---

## Table of Contents

- [Overview](#overview)
- [Project Goals](#project-goals)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running NEXUS](#running-nexus)
- [Using NEXUS](#using-nexus)
- [Voice System](#voice-system)
- [Memory and Personalization](#memory-and-personalization)
- [Tool System](#tool-system)
- [Privacy and Local Processing](#privacy-and-local-processing)
- [Troubleshooting](#troubleshooting)
- [Development Roadmap](#development-roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

NEXUS 2.0 is built around a simple principle: **an AI assistant should be able to understand a request, use relevant context, choose an appropriate response or tool, and communicate the result naturally.**

Instead of placing all functionality in one large script, NEXUS uses separate modules for language-model communication, conversation management, memory, voice input, voice output, tool execution, logging, and interface status.

This modular structure makes it easier to maintain the project, troubleshoot individual components, and introduce new capabilities without redesigning the entire application.

### What NEXUS is designed to provide

- Natural-language conversations powered by a locally hosted language model.
- Speech recognition for spoken requests.
- Spoken responses through a text-to-speech engine.
- Keyboard and voice input modes.
- Conversation-context management.
- Memory components for retaining useful information.
- A tool registry and routing layer for task-oriented functionality.
- Browser-tool integration.
- A consistent assistant personality.
- An extensible foundation for future desktop automation, vision, and wake-word activation.

## Project Goals

NEXUS is being developed around five major goals.

### 1. Local-first AI

Run language-model inference on the user's computer through Ollama, reducing reliance on paid cloud AI APIs for the core conversational experience.

### 2. Natural voice interaction

Allow users to speak to NEXUS, have their speech transcribed into text, and receive spoken responses.

### 3. Personalization and memory

Build toward an assistant that can use conversation history and relevant personal preferences to provide more context-aware responses.

### 4. Task execution

Develop a structured system through which NEXUS can identify suitable tools and carry out supported tasks instead of responding with text alone.

### 5. Modular extensibility

Keep the project organized so that future features—such as desktop control, vision, additional integrations, and more advanced planning—can be added independently.

---

## Features

### 1. Local AI conversation

NEXUS uses Ollama to communicate with a locally hosted large language model.

The AI component sends the user's message, relevant conversation context, and assistant instructions to the model, then processes the returned response.

**Capabilities include:**

- Answering general questions.
- Explaining concepts.
- Helping with programming and problem-solving.
- Generating and refining text.
- Maintaining conversational context when supported by the conversation manager.
- Running the core language-model inference locally.

The configured model can be changed in the AI client to another model supported by the installed Ollama setup.

**Current configuration:** The project has used the `llama3` model. Smaller models may be more suitable for computers with limited available memory.

### 2. Voice input and speech recognition

NEXUS includes a speech-recognition component built around Faster-Whisper.

The listener captures audio, processes the recording, and converts recognized speech into text that the assistant can handle.

**Voice-system capabilities include:**

- Capturing microphone audio.
- Transcribing spoken English.
- Using the `medium.en` Whisper model for recognition.
- Applying transcription corrections for known terms and names.
- Passing recognized speech to the assistant's processing pipeline.

Transcription quality depends on microphone quality, background noise, pronunciation, and the selected model.

### 3. Text-to-speech responses

NEXUS includes a speech-output component using Piper TTS.

After generating a response, the assistant can pass the text to the speech engine, generate audio, and play it through the computer's audio output.

**Implemented components include:**

- Local Piper executable integration.
- Neural text-to-speech model loading.
- Audio generation and playback.
- Voice parameter configuration.
- Pronunciation substitutions for selected words.

The configured voice has used Piper's `en_GB-alan-medium` model. Voice quality, accent, and naturalness depend on the selected model and its configuration.

### 4. Keyboard and voice input modes

NEXUS includes an input manager designed to handle both spoken and typed requests.

The input manager can switch between voice and keyboard modes in response to supported commands.

Examples of intended mode-switching commands include:

- `Switch to keyboard`
- `Use keyboard`
- `Switch to voice`
- `Use voice`

The exact behavior depends on the active entry point and the input-manager integration.

### 5. Conversation management

The conversation manager separates conversation history from the main assistant controller.

This allows NEXUS to maintain a structured record of messages and supply relevant context to the language model.

**Designed functionality includes:**

- Recording user messages.
- Recording assistant responses.
- Retrieving conversation context.
- Supplying recent conversation history to the AI client.

The amount of context available to the model depends on the conversation manager's configuration and the model's context window.

### 6. Memory and personalization

NEXUS includes a dedicated memory manager that separates memory-related functionality from the conversational AI layer.

The assistant's processing pipeline can submit user messages for memory processing, retrieve relevant memory context, and save conversation exchanges.

A profile-query mechanism has also been developed for requests such as:

- `What do you know about me?`
- `Tell me about myself`
- `My profile`

**Important:** Memory retrieval, durable storage, automatic fact extraction, and accurate long-term recall are separate capabilities. Their availability depends on the current memory implementation and configuration. NEXUS should not be assumed to remember every conversation or retain information across restarts unless persistent storage is correctly implemented and tested.

### 7. Tool registry and routing

NEXUS uses a tool-oriented architecture instead of embedding every task directly in the assistant's main class.

The tool registry provides a place to register available tools. The tool router handles the process of checking and executing supported tool actions.

The project includes a browser-tool component and a registry-based approach that can be extended with additional tools.

**The architecture is intended to support:**

- Registering new tools.
- Separating task logic from conversation logic.
- Routing suitable requests to supported tools.
- Returning tool results to the assistant.
- Expanding the assistant's capabilities without rewriting the entire core.

The registry and router do not automatically make every computer action available. Each action requires a working tool implementation and appropriate safeguards.

### 8. Browser-tool integration

NEXUS includes a browser-tool module intended to provide browser-related functionality through its tool system.

Its actual supported actions depend on the current implementation of `tools/browser.py`. It should not be assumed to provide unrestricted browsing, arbitrary website interaction, or fully autonomous web research unless those behaviors are implemented and verified.

### 9. Assistant personality and response refinement

NEXUS has a response-style component designed to make AI responses more consistent.

The intended personality is inspired by professional AI assistants: calm, precise, concise, and task-focused.

The response-style layer can:

- Remove selected generic introductory phrases.
- Normalize response formatting.
- Reduce excessive blank lines.
- Limit overly long line-based responses.
- Encourage a consistent assistant voice.

The language model's system instructions provide additional behavioral guidance. The final output still depends on the model and the prompts it receives.

### 10. Processing status and logging

NEXUS includes logging and status-interface components.

These components help indicate when the assistant is processing a request and record diagnostic information for development.

The project includes:

- Application logging.
- Error logging.
- A processing-status component.
- A terminal animation component.
- Cleanup of interface status during shutdown.

These features make it easier to monitor the application and investigate failures during development.

---

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Programming language | Python | Main application and module integration |
| Local AI runtime | Ollama | Runs supported language models locally |
| Language model | Llama 3 | Conversational response generation |
| Speech recognition | Faster-Whisper | Converts microphone audio into text |
| Text-to-speech | Piper TTS | Generates spoken responses |
| HTTP communication | Requests | Sends requests to the local Ollama API |
| Configuration | python-dotenv | Loads environment variables |
| Browser parsing | Beautiful Soup 4 | HTML parsing where used by the browser tools |
| Command-line utilities | Typer, Rich | Supporting command-line functionality where used |
| Logging | Python logging utilities | Diagnostic and application logs |

The exact installed dependencies may change as development continues. See [`requirements.txt`](requirements.txt) for the repository's current Python dependency list.

---

## System Architecture

The application is organized into separate components:

```text
                         ┌─────────────────────────┐
                         │       User Input        │
                         │   Voice / Keyboard      │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │       Input Layer       │
                         │  Speech / Text Handling │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │    NexusAssistant       │
                         │  Main Control Pipeline  │
                         └──────┬─────────┬────────┘
                                │         │
                   ┌────────────▼──┐   ┌──▼────────────┐
                   │ Memory Manager│   │ Tool Router   │
                   │               │   │ + Registry    │
                   └───────────────┘   └──┬────────────┘
                                          │
                                    ┌─────▼──────┐
                                    │ Browser    │
                                    │ Tool       │
                                    └────────────┘

                         ┌─────────────────────────┐
                         │     Ollama Client       │
                         │ Local Language Model    │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │ Response Style Controller│
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │ Assistant Response      │
                         │ Text / Piper Speech     │
                         └─────────────────────────┘
```

This is a conceptual view of the intended processing pipeline. The exact call sequence and available features depend on the active implementation of each module.

### Request lifecycle

1. The user provides a typed or spoken request.
2. The input layer obtains text from the keyboard or speech recognizer.
3. The assistant processes the request and records it in the conversation manager.
4. The memory component processes the request and may provide a relevant response or context.
5. The tool router checks for a supported action.
6. If no tool handles the request, the local language model generates a response.
7. The response-style controller refines the generated text.
8. The assistant records the response and can send it to Piper for speech output.
9. Status and logging components support monitoring and error diagnosis.

---

## Project Structure

The repository contains the following major components:

```text
NEXUS-2.0/
│
├── ai/
│   ├── ollama.py              # Local Ollama client
│   └── prompts.py             # AI instruction prompts
│
├── core/
│   ├── assistant.py           # Main assistant controller
│   ├── conversation.py        # Conversation context management
│   ├── input_manager.py       # Input-mode handling
│   └── response_style.py      # Response formatting and personality
│
├── integrations/              # Integration modules
├── memory/
│   └── memory_manager.py      # Memory functionality
│
├── prompts/                   # Additional prompt resources
├── tools/
│   ├── registry.py            # Tool registration
│   ├── router.py              # Tool routing
│   └── browser.py             # Browser-related functionality
│
├── ui/
│   ├── animation.py           # Terminal processing animation
│   └── status.py              # Processing status
│
├── utils/
│   └── logger.py              # Logging utilities
│
├── voice/
│   ├── listener.py            # Speech recognition
│   ├── speaker.py             # Text-to-speech
│   ├── wake_word.py           # Wake-word detection work
│   └── models/                # Voice model files
│
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
└── README.md
```

This tree highlights the principal modules. Files and subdirectories may vary slightly between commits.

---

## Requirements

Before running NEXUS, ensure that you have:

- Windows 10 or Windows 11.
- Python installed and available from the command line.
- Git installed.
- Ollama installed.
- A language model downloaded through Ollama.
- A working microphone and speakers or headphones for voice interaction.
- Sufficient available RAM and disk space for the selected language and speech models.

Speech-recognition models and local language models can require substantial storage and memory. Smaller models are generally easier to run on resource-constrained systems.

### Recommended model setup

Install Ollama from its official website:

https://ollama.com/

Then download the configured language model:

```bash
ollama pull llama3
```

Verify that Ollama can run it:

```bash
ollama run llama3
```

Keep Ollama running when you launch NEXUS. The current client communicates with the local Ollama API at:

```text
http://localhost:11434/api/chat
```

If your configuration uses a different model, download that model and update the AI client accordingly.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/rhn-007/NEXUS-2.0.git
cd NEXUS-2.0
```

### 2. Create a virtual environment

On Windows:

```bash
python -m venv venv
```

Activate it in Command Prompt:

```bat
venv\Scripts\activate
```

If you use PowerShell instead:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Some voice-related components may have additional dependencies or model files that are not listed in `requirements.txt`. Install and configure those components according to the relevant setup instructions.

### 4. Set up Ollama

Ensure the Ollama application is installed and running, then download the model configured in the AI client:

```bash
ollama pull llama3
```

Test the model before launching NEXUS:

```bash
ollama run llama3
```

Type a simple question to verify that the model responds, then exit the Ollama session.

### 5. Configure voice components

Voice input requires a compatible speech-recognition installation and the appropriate model. Voice output requires the Piper executable and a compatible `.onnx` voice model.

Check that the paths used by the voice modules match the files available on your computer.

For example, the current speaker implementation has used:

```text
piper/piper.exe
voice/models/en_GB-alan-medium.onnx
```

These files may need to be downloaded or supplied separately, depending on how the repository is distributed.

### 6. Launch NEXUS

From the repository root, with the virtual environment activated:

```bash
python main.py
```

The exact startup behavior depends on the current version of the application and the input mode configured in the assistant.

---

## Configuration

### Language model

The Ollama client is responsible for selecting the model and communicating with the local inference API.

To use another supported model, update the model setting in `ai/ollama.py` and ensure that the model has been downloaded.

### Speech recognition

The listener configuration determines the Whisper model, device, audio settings, and transcription options.

The `medium.en` model has been used during development. A smaller model may reduce resource requirements, while a larger model may improve recognition in some situations.

### Text-to-speech

The speaker configuration determines the Piper executable, voice model, and speech-generation parameters.

A different compatible Piper voice can be selected by changing the model path and testing the resulting speech quality.

### Environment variables

The project includes `python-dotenv`, allowing configuration values to be loaded from a `.env` file where implemented.

If your local setup requires environment variables, create a `.env` file based on the configuration expected by the relevant modules.

**Never commit API keys, passwords, authentication tokens, or other secrets to GitHub.** Keep private configuration files out of version control.

---

## Running NEXUS

### Start the local AI service

Ensure Ollama is running and the configured model is available.

### Start the assistant

From the project root:

```bash
python main.py
```

### End a session

If the active command loop supports it, enter:

```text
exit
```

or:

```text
quit
```

You can also use `Ctrl+C` to interrupt the application.

---

## Using NEXUS

Once NEXUS is running, you can test the conversational pipeline with ordinary requests.

### General questions

```text
Explain how a neural network learns.
```

```text
What is the difference between supervised and unsupervised learning?
```

### Programming assistance

```text
Explain this Python error.
```

```text
Help me understand how a Python class works.
```

### Conversation and personalization

```text
What do you know about me?
```

```text
Tell me about myself.
```

These examples exercise the conversational and memory-query paths. The accuracy and completeness of responses depend on the model, current conversation context, and memory implementation.

### Input-mode switching

Where the input manager is active, try commands such as:

```text
Switch to keyboard
```

```text
Switch to voice
```

Voice recognition and command handling depend on the microphone, audio environment, and active input configuration.

---

## Voice System

The voice system is divided into separate components.

| Component | Responsibility |
|---|---|
| `voice/listener.py` | Captures and transcribes spoken input |
| `voice/speaker.py` | Generates and plays spoken responses |
| `voice/wake_word.py` | Wake-word detection functionality |
| `voice/models/` | Speech model assets |

### Wake-word detection

Wake-word detection is an important part of the NEXUS hands-free interaction plan.

The project includes a wake-word module and has explored OpenWakeWord for detection. A reliable custom **“Hey NEXUS”** model requires its own suitable training or verification workflow; installing a wake-word library alone does not guarantee that a custom phrase is recognized.

Custom model training, model compatibility, false-trigger testing, and integration with the main listening loop remain areas to verify before treating hands-free activation as a finished feature.

---

## Memory and Personalization

Memory is intended to help NEXUS make use of information beyond the current message.

The memory layer is kept separate from the language-model client so that storage and retrieval can be improved independently.

Future memory improvements are intended to include:

- Persistent personal preferences.
- Reliable recall of relevant facts.
- Separate project-specific context.
- Better retrieval of relevant past conversations.
- User-controlled inspection and deletion of saved information.

These are development goals, not a guarantee that every item is fully implemented in the current version.

---

## Tool System

NEXUS separates tools from the assistant's conversational logic.

The tool registry stores registered tool implementations, while the router provides a central place to check and execute supported actions.

This design can be extended with tools for:

- Browser interaction.
- File and folder operations.
- Desktop application control.
- System information.
- External services.
- Other user-approved automations.

Each additional capability requires an implementation, appropriate permissions, error handling, and testing. Listing a possible tool category here does not mean that NEXUS already supports every action in that category.

---

## Privacy and Local Processing

NEXUS is designed with a local-first approach to AI inference.

When the assistant uses Ollama on the same computer, the language-model request is processed by the local Ollama service rather than automatically being sent to a hosted language-model API.

However, **local AI inference does not mean every part of the application is automatically offline**. Installing dependencies, downloading models, using online websites, and adding external integrations may require an internet connection or transmit data to third-party services.

Before using NEXUS with sensitive information:

- Review the code of any enabled integrations.
- Check which services receive requests.
- Protect credentials and authentication tokens.
- Avoid committing private data or configuration files.
- Use only tools and permissions you understand.

---

## Troubleshooting

### Ollama connection error

Check that Ollama is installed and running.

Verify the configured model:

```bash
ollama list
```

Test it directly:

```bash
ollama run llama3
```

If the model fails to load, check available RAM, disk space, and the model's resource requirements.

### Slow AI responses

Local inference speed depends on the model size, hardware, available memory, and other running applications. Try a smaller compatible model if necessary.

### Speech recognition is inaccurate

- Reduce background noise.
- Check microphone input levels.
- Speak clearly.
- Verify that the intended Whisper model is installed and selected.
- Review transcription corrections in the listener module.

### No spoken response

- Check that the Piper executable exists at the configured path.
- Verify that the voice model file is available.
- Test audio playback independently.
- Check the console logs for speaker errors.
- Verify that the current assistant flow calls the speech-output component.

### Wake-word detection does not respond

- Confirm that the wake-word module loads correctly.
- Check microphone access and audio capture.
- Verify that the intended model file is present.
- Test the detector separately from the main assistant.
- For a custom wake word, confirm that a trained compatible model exists and has been integrated.

### Missing Python module

Ensure that the virtual environment is activated and install the repository's listed dependencies:

```bash
pip install -r requirements.txt
```

If an error refers to a dependency not listed in `requirements.txt`, identify the module that requires it before installing additional packages.

---

## Development Roadmap

NEXUS is an evolving personal AI project. The roadmap below distinguishes existing foundations from future goals.

### Core assistant

- [x] Python-based assistant controller.
- [x] Local Ollama integration.
- [x] Conversation-management component.
- [x] Response-style controller.
- [x] Logging and processing-status components.
- [ ] More comprehensive automated tests.
- [ ] Improved error recovery and diagnostics.

### Voice interaction

- [x] Speech-recognition component.
- [x] Piper text-to-speech component.
- [x] Voice and keyboard input-mode logic.
- [ ] Reliable end-to-end hands-free activation.
- [ ] Verified custom “Hey NEXUS” wake-word model.
- [ ] Improved speech naturalness and interruption handling.

### Memory

- [x] Dedicated memory-manager component.
- [x] Memory processing and retrieval hooks.
- [ ] More reliable persistent long-term memory.
- [ ] Structured personal-preference storage.
- [ ] Project-specific memory.
- [ ] Better retrieval, editing, and deletion controls.

### Tools and automation

- [x] Tool registry.
- [x] Tool router.
- [x] Browser-tool component.
- [ ] Broader verified browser actions.
- [ ] File and folder management tools.
- [ ] Desktop application control.
- [ ] System-control tools with appropriate safeguards.
- [ ] Improved planning and multi-step task execution.

### Vision and extensibility

- [ ] Screenshot understanding.
- [ ] Image and object analysis.
- [ ] Assistance with coding and robotics workflows.
- [ ] Additional integrations.
- [ ] More robust permissions and confirmation before consequential actions.

Roadmap checkboxes should be updated as features are implemented and tested. In particular, a component being present in the repository is not by itself proof that the entire user-facing feature is complete.

---

## Contributing

NEXUS is a personal AI assistant project under active development. Suggestions, bug reports, and improvements are welcome.

If you would like to contribute:

1. Fork the repository.
2. Create a branch for your change.
3. Keep changes modular and consistent with the existing architecture.
4. Test the affected functionality.
5. Submit a pull request describing the change and its behavior.

For bugs, include the relevant error message, operating system, Python version, and steps to reproduce the issue. Do not include API keys, credentials, or other private information.

---

## License

A license has not been specified in this README. Check the repository for a `LICENSE` file before deciding how the project may be reused or redistributed.

---

## Author

**Rohan** — Creator and developer of NEXUS 2.0.

GitHub: [@rhn-007](https://github.com/rhn-007)

---

*NEXUS 2.0 is an ongoing project focused on building a personal AI assistant that combines local AI, voice interaction, memory, and task-oriented tools in a modular system.*
