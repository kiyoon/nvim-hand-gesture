FROM nvidia/cuda:11.4.1-devel-ubuntu18.04

# Prevents apt-get to show interactive screen
ARG DEBIAN_FRONTEND=noninteractive

# Needed for string substitution
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
		git \
		wget \
		neovim \
		tzdata \
		&& \
		apt-get clean && \
		rm -rf /var/lib/apt/lists/*

ENV LD_LIBRARY_PATH /usr/local/cuda/lib64:$LD_LIBRARY_PATH
ENV PATH /usr/local/cuda/bin:$PATH
ENV TZ=Europe/London
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
ENV LANG C.UTF-8

RUN cd && wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \
	bash Miniconda3-latest-Linux-x86_64.sh -b -p /opt/conda && \
	rm Miniconda3-latest-Linux-x86_64.sh && \
	/opt/conda/bin/conda init bash

RUN /opt/conda/bin/conda create -n tsm -y python=3.8

# Make RUN commands use the new environment:
SHELL ["/opt/conda/bin/conda", "run", "--no-capture-output", "-n", "tsm", "/bin/bash", "-c"]

RUN conda install -y pytorch==1.10.1 torchvision==0.11.2 torchaudio==0.10.1 cudatoolkit=11.3 -c pytorch -c conda-forge && \
	conda clean -ya

# Install OpenCV
RUN conda install mamba -n base -c conda-forge -y && \
	mamba install -y opencv -c conda-forge && \
	conda clean -ya

RUN apt-get update && apt-get install -y llvm-8 \
	cmake \
	libgl1 && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/*

RUN git clone -b v0.6 https://github.com/apache/incubator-tvm.git && \
	cd incubator-tvm && \
	git submodule update --init && \
	mkdir build && \
	cp cmake/config.cmake build/ && \
	cd build

RUN cd incubator-tvm/build && \
	sed -i 's/USE_CUDA OFF/USE_CUDA ON/' config.cmake && \
	sed -i 's/USE_LLVM OFF/USE_LLVM ON/' config.cmake && \
	cmake .. && \
	make -j$(nproc) && \
	cd ../python && \
	pip install . && \
	cd ../topi/python && \
	pip install .

# install onnx
RUN apt-get update && apt-get install protobuf-compiler libprotoc-dev -y && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/*
RUN pip3 install onnx onnxsim mpmath flatbuffers sympy packaging humanfriendly coloredlogs onnxruntime pynvim

RUN wget https://hanlab.mit.edu/projects/tsm/models/mobilenetv2_jester_online.pth.tar -P /

WORKDIR /workspace
ENTRYPOINT ["/opt/conda/bin/conda", "run", "--no-capture-output", "-n", "tsm", "python", "main.py"]
