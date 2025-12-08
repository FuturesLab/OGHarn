CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

LIB_NAME = lib
LIB_REPO = https://github.com/file/file.git

DEPS = -I $(PWD)/$(LIB_NAME)/src/ \
	   -L $(PWD)/$(LIB_NAME)/src/.libs

DEPS_DYN = -l magic
DEPS_STC = -l:libmagic.a -llzma -lbz2 -lz -lzstd
DEPS_LDD = $(PWD)/$(LIB_NAME)/src/.libs/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1
	export AFL_USE_UBSAN=1
	rm -rf $(LIB_NAME)
	git clone $(LIB_REPO) $(LIB_NAME)
	cd $(LIB_NAME) && \
	git checkout 0fa2c8c3e64c372d038d46969bafaaa09a13a87b && \
	autoreconf -i && ./configure \
	CC=$(CC_FUZZ) CXX=$(CC_FUZZ) --enable-static && \
	make all -j12

lib_plain: # Build for indexing with multiplier 
	export AFL_USE_ASAN=1
	export AFL_USE_UBSAN=1
	rm -rf $(LIB_NAME)_plain
	git clone $(LIB_REPO) $(LIB_NAME)_plain
	cd $(LIB_NAME)_plain && \
	git checkout 0fa2c8c3e64c372d038d46969bafaaa09a13a87b && \
	autoreconf -i && ./configure \
	CC=$(CC) CXX=$(CXX) && \
	bear -- make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout 0fa2c8c3e64c372d038d46969bafaaa09a13a87b && \
	autoreconf -i && ./configure \
	CC=$(CC_FUZZ) CXX=$(CXX_FUZZ) --enable-static && \
	make all -j12

run_mx:
	mx-index --db $(PWD)/$(LIB_NAME).db --target $(PWD)/$(LIB_NAME)_plain/compile_commands.json --workspace $(PWD)/mx
	
#------------------------------------------------------------------------
all: lib lib_plain lib_fuzz run_mx
	
#------------------------------------------------------------------------
harness: # make command used to make the harness during generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c $(DEPS) $(DEPS_DYN) $(CFLAGS_ASAN)

showmap: # command used to get coverage information about library under test
	LD_LIBRARY_PATH=$(DEPS_LDD) MAGIC=$(PWD)/lib/magic/magic.mgc afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)

harness_fuzz: # compile a harness specifically for fuzzing. Pass the harness number using make harness_fuzz HARNESS_NUMBER=x
	@ls bin || mkdir bin 
	$(eval LIB_NAME=lib_fuzz) \
	$(CC_FUZZ) -o bin/ogharn$(HARNESS_NUMBER)\_fuzz $(OUT)/final-harnesses/src/harness$(HARNESS_NUMBER):*.c -static $(DEPS) $(DEPS_STC) ;

clean:
	rm -rf bin mx lib.db-*

clean_lib:
	rm -rf $(LIB_NAME)* 