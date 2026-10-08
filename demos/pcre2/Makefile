CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

LIB_NAME = lib
LIB_REPO = https://github.com/PCRE2Project/pcre2.git

DEPS = -I $(PWD)/$(LIB_NAME)/ \
	   -I $(PWD)/$(LIB_NAME)/src \
	   -L $(PWD)/$(LIB_NAME)/ \

DEPS_DYN = -l:libpcre2-8.a
DEPS_STC = -l:libpcre2-8.a
DEPS_LDD = $(PWD)/$(LIB_NAME)/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout a67878318cd08eb92e7f3afa2a15b55d46d285e2 && \
	cmake . \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ)  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && \
	make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout a67878318cd08eb92e7f3afa2a15b55d46d285e2 && \
	cmake . \
	-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DBUILD_SHARED_LIBS=Off && \
	make all -j12

run_mx: # Use Multiplier to index the library
	mx-index --db $(PWD)/$(LIB_NAME).db --target $(PWD)/$(LIB_NAME)/compile_commands.json --workspace $(PWD)/mx

#------------------------------------------------------------------------
all: lib lib_fuzz run_mx
	
#------------------------------------------------------------------------
harness: # make command used to make the harness during generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c $(DEPS) $(DEPS_DYN) $(CFLAGS_ASAN)

harness_static: # command used to statically compile harness during harness generation
	$(CC_FUZZ)  -o $(OUT)/harness.out $(OUT)/harness.c  -static $(DEPS) $(DEPS_DYN) 

showmap: # command used to get coverage information about library under test
	LD_LIBRARY_PATH=$(DEPS_LDD) afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)

showmap_static:
	afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)

harness_fuzz: # compile a harness specifically for fuzzing. Pass the harness number using make harness_fuzz HARNESS_NUMBER=x
	@ls bin || mkdir bin 
	$(eval LIB_NAME=lib_fuzz) \
	$(CC_FUZZ) -o bin/ogharn$(HARNESS_NUMBER)\_fuzz $(OUT)/final-harnesses/src/harness$(HARNESS_NUMBER):*.c -static $(DEPS) $(DEPS_STC) ;

clean:
	rm -rf bin mx lib.db-*

clean_lib:
	rm -rf $(LIB_NAME)* 

