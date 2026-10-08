CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

LIB_NAME = lib
LIB_REPO = https://github.com/gpac/gpac

DEPS = -I $(PWD)/$(LIB_NAME)/include/ \
	   -I $(PWD)/$(LIB_NAME)/ \
	   -L $(PWD)/$(LIB_NAME)/bin/gcc/

DEPS_DYN = -lgpac
DEPS_STC = -l:libgpac_static.a -lm -lssl -lcrypto -lz -lGLU -lGL -lpng -ljpeg -lvorbis -llzma
DEPS_LDD = $(PWD)/$(LIB_NAME)/bin/gcc

# NEED TO REPLACE lib/include/gpac/configuration.h with lib/config.h

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation -- cp statement at bottom since config file isn't happy
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout 5d70253ac94e5840be7b86054131dd753af63cc7 && \
	patch -u include/gpac/internal/isomedia_dev.h \
		-i ../patch.diff && \
	./configure --enable-static \
		--cc=$(CC_FUZZ) --cxx=$(CXX_FUZZ) && \
	make all -j12
	cp $(LIB_NAME)/config.h $(LIB_NAME)/include/gpac/configuration.h 
	
lib_plain: # build for indexing with multiplier
	rm -rf $(LIB_NAME)_plain
	git clone $(LIB_REPO) $(LIB_NAME)_plain
	cd $(LIB_NAME)_plain && \
	git checkout 5d70253ac94e5840be7b86054131dd753af63cc7 && \
	patch -u include/gpac/internal/isomedia_dev.h \
		-i ../patch.diff && \
	./configure --enable-static && \
	bear -- make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation -- cp statement at bottom since config file isn't happy
	rm -rf $(LIB_NAME)
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout 5d70253ac94e5840be7b86054131dd753af63cc7 && \
	patch -u include/gpac/internal/isomedia_dev.h \
		-i ../patch.diff && \
	./configure --enable-static \
		--cc=$(CC_FUZZ) --cxx=$(CXX_FUZZ) && \
	make all -j12
	cp $(LIB_NAME)_fuzz/config.h $(LIB_NAME)_fuzz/include/gpac/configuration.h  

run_mx: # Use Multiplier to index the library
	mx-index --db $(PWD)/$(LIB_NAME).db --target $(PWD)/$(LIB_NAME)_plain/compile_commands.json --workspace $(PWD)/mx

#------------------------------------------------------------------------
all: lib lib_plain lib_fuzz run_mx
	
#------------------------------------------------------------------------
harness: # make command used to make the harness during generation
	$(CC_FUZZ) -o $(OUT)/harness.out $(OUT)/harness.c $(DEPS) $(CFLAGS_ASAN)

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