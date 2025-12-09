FROM ubuntu:24.04
WORKDIR /
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies for multiplier 
RUN apt-get update \
    && apt-get install -y sudo \
    && apt-get install -y wget \
    && apt-get install -y git \
    && apt-get install --no-install-recommends -y curl gnupg software-properties-common lsb-release build-essential libgoogle-glog-dev \
    && apt-get install -y tzdata \
    && ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime \
    && echo "Etc/UTC" > /etc/timezone \
    && dpkg-reconfigure -f noninteractive tzdata \
    && sudo add-apt-repository ppa:deadsnakes/ppa \
    && sudo apt install python3.12-dev python3.12-venv -y \
    && sudo apt update \
    && sudo apt clean all \
    && wget https://apt.llvm.org/llvm.sh \
    && chmod u+x llvm.sh \
    && sudo ./llvm.sh 18 \
    && sudo apt install lld-18 lld -y \
    && wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | sudo tee /etc/apt/trusted.gpg.d/kitware.gpg >/dev/null \
    && sudo apt-add-repository "deb https://apt.kitware.com/ubuntu/ $(lsb_release -cs) main" \
    && sudo apt update \
    && apt-get install --no-install-recommends -y \
        gpg zip unzip tar git \
        pkg-config ninja-build ccache build-essential \
        doctest-dev \
        clang-18 lld-18 \
        python3.11 python3.11-dev \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/Kitware/CMake/releases/download/v3.31.6/cmake-3.31.6-linux-x86_64.tar.gz \
    && (apt-get remove -y cmake || true) \
    && tar xz -f cmake-3.31.6-linux-x86_64.tar.gz -C /opt \
    && ln -s /opt/cmake-3.31.6-linux-x86_64/bin/cmake /usr/local/bin/cmake \
    && ln -s /opt/cmake-3.31.6-linux-x86_64/bin/cmake /usr/bin/cmake

# download and set up multiplier
RUN mkdir -p /OGHarn/extras/multiplier/install
COPY . /OGHarn
WORKDIR /OGHarn/extras/multiplier
RUN wget https://github.com/trailofbits/multiplier/releases/download/e137812/multiplier-e137812.tar.xz \
    && tar -xf multiplier-e137812.tar.xz
RUN mv bin install

# set up AFLplusplus
RUN git clone https://github.com/AFLplusplus/AFLplusplus /AFLplusplus
WORKDIR /AFLplusplus
RUN make all -j $(nproc)
RUN make install

# install bear for indexing 
RUN sudo apt-key adv --fetch-keys https://apt.kitware.com/keys/kitware-archive-latest.asc \
    && sudo apt update \
    && sudo apt install -y bear

WORKDIR /OGHarn/extras
RUN python3.12 -m venv .venv