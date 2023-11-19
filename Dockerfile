FROM mcr.microsoft.com/devcontainers/base:bullseye

# Persist pre-commit cache
ENV PRE_COMMIT_HOME=/pre-commit-cache
RUN mkdir /pre-commit-cache \
  && chown vscode /pre-commit-cache

# Persist Bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/command-history/.bash_history" \
  && mkdir /command-history \
  && touch /command-history/.bash_history \
  && chown -R vscode /command-history \
  && echo "$SNIPPET" >> "/home/vscode/.bashrc"
