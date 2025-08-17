FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    sudo \
    openssh-server \
    nano \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash student && \
    echo "student:student" | chpasswd && \
    adduser student sudo

WORKDIR /home/student

CMD ["/bin/bash"]
