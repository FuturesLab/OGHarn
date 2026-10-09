CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

#------------------------------------------------------------------------
# Edit these below accordingly...

LIB_NAME = lib
LIB_REPO = https://github.com/vstakhov/libucl

DEPS = -I $(PWD)/$(LIB_NAME)/ \
	   -I $(PWD)/$(LIB_NAME)/include \
	   -I $(PWD)/$(LIB_NAME)/src \
	   -I $(PWD)/$(LIB_NAME)/uthash \
	   -L $(PWD)/$(LIB_NAME)/

DEPS_DYN = -lucl
DEPS_STC = -l:libucl.a
DEPS_LDD = $(PWD)/$(LIB_NAME)/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout 51c5e2f0526c41efc5e919e0b834a87b1976f33c && \
	cmake . \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DBUILD_SHARED_LIBS=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && \
	make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout 51c5e2f0526c41efc5e919e0b834a87b1976f33c && \
	cmake . \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DBUILD_SHARED_LIBS=OFF && \
	make all -j12

run_mx: # Use Multiplier to index the library
	mx-index --db $(PWD)/$(LIB_NAME).db --target $(PWD)/$(LIB_NAME)/compile_commands.json --workspace $(PWD)/mx

#------------------------------------------------------------------------
all: lib lib_fuzz run_mx
	
#------------------------------------------------------------------------
harness: # make command used to make the harness during generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c $(DEPS) $(DEPS_DYN) $(CFLAGS_ASAN)

showmap: # command used to get coverage information about library under test
	LD_LIBRARY_PATH=$(DEPS_LDD) afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)

harness_fuzz: # compile a harness specifically for fuzzing. Pass the harness number using make harness_fuzz HARNESS_NUMBER=x
	@ls bin || mkdir bin 
	$(eval LIB_NAME=lib_fuzz) \
	$(CC_FUZZ) -o bin/ogharn$(HARNESS_NUMBER)\_fuzz $(OUT)/final-harnesses/src/harness$(HARNESS_NUMBER):*.c -static $(DEPS) $(DEPS_STC) ;

clean:
	rm -rf bin mx lib.db-*

clean_lib:
	rm -rf $(LIB_NAME)* 