#------------------------------------------------------------------------
# Leave these as-is (unless you must change the compiler)!
CC				= clang-18
CXX				= clang++-18
CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

#------------------------------------------------------------------------
# Edit these below accordingly...

LIB_NAME = lib
LIB_REPO = https://github.com/libical/libical

DEPS = -I $(PWD)/$(LIB_NAME)/src/ \
	   -I $(PWD)/$(LIB_NAME)/lib/ \
	   -L $(PWD)/$(LIB_NAME)/lib/ 

DEPS_DYN = -lical
DEPS_STC = -l:libical.a -licui18n -licuuc -licudata -lstdc++ -lm
DEPS_LDD = $(PWD)/$(LIB_NAME)/lib/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout 460b8d71e70ceb1b88bca6ce8d3aefb2ace05900 && \
	cmake . \
		-DICAL_GLIB_BUILD_DOCS=False -DENABLE_GTK_DOC=OFF -DGOBJECT_INTROSPECTION=False \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && \
	make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout 460b8d71e70ceb1b88bca6ce8d3aefb2ace05900 && \
	cmake . \
		-DENABLE_GTK_DOC=OFF \
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