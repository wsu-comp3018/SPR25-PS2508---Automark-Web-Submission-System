FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    sudo \
    openssh-server \
    nano \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd

# Create a user 'student' with password 'student' and add to sudoers
RUN useradd -ms /bin/bash student && \
    echo "student:student" | chpasswd && \
    adduser student sudo

RUN groupadd -f student && usermod -aG student student

# Create parent dirs, lock them to root:root and no group write
RUN mkdir -p /home/student/2025/AUT/PX \
    /home/student/2025/SPR/PX && \
    chown root:root /home/student/2025 /home/student/2025/AUT /home/student/2025/SPR \
    /home/student/2025/AUT/PX /home/student/2025/SPR/PX && \
    chmod 755 /home/student/2025 /home/student/2025/AUT /home/student/2025/SPR \
    /home/student/2025/AUT/PX /home/student/2025/SPR/PX

# Create assignment directories owned by root:student, student can write files but not remove folder
RUN mkdir -p /home/student/2025/AUT/PX/Assignment1 \
    /home/student/2025/AUT/PX/Assignment2 \
    /home/student/2025/SPR/PX/Assignment1 \
    /home/student/2025/SPR/PX/Assignment2 && \
    chown root:student /home/student/2025/AUT/PX/Assignment1 /home/student/2025/AUT/PX/Assignment2 \
    /home/student/2025/SPR/PX/Assignment1 /home/student/2025/SPR/PX/Assignment2 && \
    chmod 1770 /home/student/2025/AUT/PX/Assignment1 /home/student/2025/AUT/PX/Assignment2 \
    /home/student/2025/SPR/PX/Assignment1 /home/student/2025/SPR/PX/Assignment2
    
# Allow password authentication for SSH
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Set TimeZone
RUN ln -sf /usr/share/zoneinfo/Australia/Sydney /etc/localtime

EXPOSE 22

CMD ["/usr/sbin/sshd","-D"]
