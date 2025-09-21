FROM ubuntu:22.04

# Install SVN server and utilities
RUN apt-get update && apt-get install -y \
    subversion \
    apache2 \
    libapache2-mod-svn \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create SVN directories
RUN mkdir -p /var/svn/repositories \
    && mkdir -p /var/svn/templates \
    && mkdir -p /var/submissions \
    && mkdir -p /var/svn/hooks

# Create SVN configuration
COPY svnserve.conf /etc/subversion/
COPY passwd /etc/subversion/
COPY authz /etc/subversion/

# Copy initialization and hook scripts
COPY init-svn.sh /usr/local/bin/
COPY post-commit-hook.py /var/svn/hooks/
RUN chmod +x /usr/local/bin/init-svn.sh \
    && chmod +x /var/svn/hooks/post-commit-hook.py

# Set permissions
RUN chown -R www-data:www-data /var/svn \
    && chown -R www-data:www-data /var/submissions

# Expose SVN port
EXPOSE 3690

# Initialize SVN repositories and start server
CMD ["/usr/local/bin/init-svn.sh"]
