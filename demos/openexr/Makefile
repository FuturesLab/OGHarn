CC_FUZZ       	= afl-clang-fast
CXX_FUZZ      	= afl-clang-fast++
CFLAGS_ASAN 	= -fsanitize=address,undefined
CXXFLAGS_ASAN 	= -fsanitize=address,undefined

LIB_NAME = lib
LIB_REPO = https://github.com/AcademySoftwareFoundation/openexr

DEPS = -I $(PWD)/$(LIB_NAME)/src/lib/OpenEXR \
	   -I $(PWD)/$(LIB_NAME)/src/lib/OpenEXRUtil/ \
	   -I $(PWD)/$(LIB_NAME)/cmake \
	   -L $(PWD)/$(LIB_NAME)/src/lib/OpenEXR/ \
	   -L $(PWD)/$(LIB_NAME)/src/lib/IlmThread/ \
	   -L $(PWD)/$(LIB_NAME)/src/lib/Iex/ \
	   -L $(PWD)/$(LIB_NAME)/_deps/imath-build/src/Imath \
	   -L $(PWD)/$(LIB_NAME)/src/lib/OpenEXRCore/ \
	   -L $(PWD)/$(LIB_NAME)/src/lib/OpenEXRUtil/

DEPS_DYN = -lOpenEXR -lOpenEXRUtil
DEPS_STC = -l:libOpenEXRUtil-3_3.a -l:libOpenEXR-3_3.a -l:libOpenEXRCore-3_3.a -l:libIex-3_3.a -l:libIlmThread-3_3.a -l:libImath-3_2.a -lstdc++ -lm -ldeflate
DEPS_LDD = $(PWD)/$(LIB_NAME)/src/lib/OpenEXR:$(PWD)/$(LIB_NAME)/src/lib/OpenEXRUtil/:$(PWD)/$(LIB_NAME)/src/lib/OpenEXRCore/

#------------------------------------------------------------------------
lib: # build for harness generation. Dynamic linking, asan, and afl instrumentation
	export AFL_USE_ASAN=1 && \
	export AFL_USE_UBSAN=1 && \
	rm -rf $(LIB_NAME) && \
	git clone $(LIB_REPO) $(LIB_NAME) && \
	cd $(LIB_NAME) && \
	git checkout d669510fda59ac26dc183e8bc271208c0eb737ad && \
	cmake . \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTING=OFF \
		BUILD_TESTING=OFF && \
	make all -j12

lib_fuzz: # build for fuzzing. Static linking with afl instrumentation
	rm -rf $(LIB_NAME)_fuzz
	git clone $(LIB_REPO) $(LIB_NAME)_fuzz
	cd $(LIB_NAME)_fuzz && \
	git checkout d669510fda59ac26dc183e8bc271208c0eb737ad && \
	cmake . \
		-DCMAKE_C_COMPILER=$(CC_FUZZ) -DCMAKE_CXX_COMPILER=$(CXX_FUZZ) -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF && \
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