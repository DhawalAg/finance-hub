FROM python:3.12-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
  git \
  curl \
  jq \
  && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && apt-get update && apt-get install -y gh \
  && rm -rf /var/lib/apt/lists/*

# Build-args for UID/GID alignment: sandcastle docker build-image
# defaults these to the host user's UID/GID so image-built files
# and bind-mounted files share an owner without runtime chown.
ARG AGENT_UID=1000
ARG AGENT_GID=1000

# Create the sandbox user and align UID/GID with the host user.
RUN groupadd -o -g $AGENT_GID agent \
  && useradd -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -s /bin/bash agent
USER ${AGENT_UID}:${AGENT_GID}

# Create a user-owned virtualenv so agents can install the project editable.
ENV VIRTUAL_ENV=/home/agent/venv
RUN python -m venv $VIRTUAL_ENV

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Add the virtualenv and Claude Code CLI to PATH.
ENV PATH="$VIRTUAL_ENV/bin:/home/agent/.local/bin:$PATH"

WORKDIR /home/agent

# In worktree sandbox mode, Sandcastle bind-mounts the git worktree at /home/agent/workspace
# and overrides the working directory to /home/agent/workspace at container start.
# Structure your Dockerfile so that /home/agent/workspace can serve as the project root.
ENTRYPOINT ["sleep", "infinity"]
