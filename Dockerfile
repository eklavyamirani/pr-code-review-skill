# Everything runs in here. The host contributes a read-only bind mount of the
# repository and an output directory; nothing else is touched, and the PR's
# code never executes outside this container.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git zsh bash ca-certificates less \
 && rm -rf /var/lib/apt/lists/*

# Non-root: a traced PR script that decides to `rm -rf $HOME` should hit a
# throwaway home, not the container's root filesystem.
RUN useradd -m -s /bin/bash reviewer
COPY scripts/   /opt/pr-review/scripts/
COPY templates/ /opt/pr-review/templates/
RUN chmod +x /opt/pr-review/scripts/*.sh /opt/pr-review/scripts/*.py

ENV PR_REVIEW_HOME=/opt/pr-review \
    PATH=/opt/pr-review/scripts:$PATH \
    HOME=/home/reviewer

# /work is normally a bind mount from the host (see bin/pr-review) and the
# container runs as an arbitrary host uid, so the mountpoint itself must be
# writable by whoever that turns out to be.
RUN mkdir -p /work && chmod 1777 /work

USER reviewer
WORKDIR /work
ENTRYPOINT ["/opt/pr-review/scripts/entrypoint.sh"]
