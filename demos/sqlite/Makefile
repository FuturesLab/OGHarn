#------------------------------------------------------------------------
# Leave these as-is (unless you must change the compiler)!

CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CC 				= clang
CXX				= clang++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

#------------------------------------------------------------------------
# Edit these below accordingly...

LIB_NAME = lib
LIB_REPO = https://github.com/sqlite/sqlite.git

DEPS = -I $(PWD)/$(LIB_NAME)/ \
	   -L $(PWD)/$(LIB_NAME)/
	   
DEPS_STAT = -I $(PWD)/$(LIB_NAME)_static/ \
	  		-L $(PWD)/$(LIB_NAME)_static/

DEPS_DYN = -lsqlite3
DEPS_STC = -l:libsqlite3.a -lm
DEPS_LDD = $(PWD)/$(LIB_NAME)/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout 0df847cc776131919935658230fe2e629906dabb && \
	./configure \
	CC=$(CC_FUZZ) CXX=$(CXX_FUZZ) \
	CFLAGS="-DSQLITE_ENABLE_API_ARMOR" \
	CXXFLAGS="-DSQLITE_ENABLE_API_ARMOR" && \
	make all -j12

lib_plain: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	rm -rf $(LIB_NAME)_plain
	git clone $(LIB_REPO) $(LIB_NAME)_plain
	cd $(LIB_NAME)_plain && \
	git checkout 0df847cc776131919935658230fe2e629906dabb && \
	./configure \
	CC=$(CC) CXX=$(CXX) \
	CFLAGS="-DSQLITE_ENABLE_API_ARMOR" \
	CXXFLAGS="-DSQLITE_ENABLE_API_ARMOR" && \
	bear -- make all -j12

lib_static:
	rm -rf $(LIB_NAME)_static
	git clone $(LIB_REPO) $(LIB_NAME)_static
	cd $(LIB_NAME)_static && \
	git checkout 0df847cc776131919935658230fe2e629906dabb && \
	./configure --static \
	CC=$(CC_FUZZ) CXX=$(CXX_FUZZ) \
	CFLAGS="-DSQLITE_ENABLE_API_ARMOR" \
	CXXFLAGS="-DSQLITE_ENABLE_API_ARMOR" && \
	make all -j12


lib_fuzz:  # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout 0df847cc776131919935658230fe2e629906dabb && \
	./configure --static --with-tclsh=/usr/bin/tclsh8.6 \
	CC=$(CC_FUZZ) CXX=$(CXX_FUZZ) \
	CFLAGS="-DSQLITE_ENABLE_API_ARMOR" \
	CXXFLAGS="-DSQLITE_ENABLE_API_ARMOR" && \
	make all -j12

run_mx: # Use Multiplier to index the library
	mx-index --db $(PWD)/$(LIB_NAME).db --target $(PWD)/$(LIB_NAME)_plain/compile_commands.json --workspace $(PWD)/mx
	
#------------------------------------------------------------------------
all: lib lib_plain lib_fuzz run_mx
	
#------------------------------------------------------------------------
harness: # make command used to make the harness during generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c $(DEPS) $(DEPS_DYN) $(CFLAGS_ASAN)

harness_static: # command used to statically compile harness during harness generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c -static $(DEPS) $(DEPS_STC) 

showmap: # command used to get coverage information about library under test
	LD_LIBRARY_PATH=$(DEPS_LDD) afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)

showmap_static: # command used to get coverage information about the statically linked harness
	afl-showmap -o $(OUT)/tempfile -- $(OUT)/harness.out $(SEED)


harness_fuzz: # compile a harness specifically for fuzzing. Pass the harness number using make harness_fuzz HARNESS_NUMBER=x
	@ls bin || mkdir bin 
	$(eval LIB_NAME=lib_fuzz) \
	$(CC_FUZZ) -o bin/ogharn$(HARNESS_NUMBER)\_fuzz $(OUT)/final-harnesses/src/harness$(HARNESS_NUMBER):*.c -static $(DEPS) $(DEPS_STC) ;

clean:
	rm -rf bin mx lib.db-*

clean_lib:
	rm -rf $(LIB_NAME)* 