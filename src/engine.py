import cfile as C
import shutil
from copy import deepcopy
import multiplier as mx
import random
import string
import subprocess
import time
import pathlib
import os
import sys

"""Represents a function contained in the header file of an api:
    -name represents the name of the function
    -args represents the ordered arguments and their types that the function expects
    -retType represents the return type of the function
    -statusCheck represents whether the variable this function is set to needs to be compared with another value after the function call
    -statusCheckComparison represents the value the variable should be compared with if the statusCheck parameter is true"""


class Function:
    def __init__(self, name, mult_args, mult_ret, category="processing"):
        self.name = name
        self.category = category
        self.mult_args = mult_args
        self.mult_ret = mult_ret
        self.dependencies = []
        self.reverseDependencies = []
        self.ret_status_check = "no-check", None
        self.potential_arguments = [set() for i in range(0, len(self.mult_args))]
        self.fuzz_args = dict()

    def addDependency(self, dependency):
        self.dependencies.append(dependency)

    def addReverseDependency(self, dependency):
        self.reverseDependencies.append(dependency)

    def __str__(self):
        retstring = self.name + "\nDependencies:\n"
        for dep in self.dependencies:
            retstring += str(dep) + "\n"
        return retstring[:-1]


class APIfunctions:
    def __init__(self):
        self.auxiliaryFunctions = dict()
        self.setupFunctions = dict()
        self.processingFunctions = dict()
        self.classFunctions = dict()

    def addAuxiliaryFunction(self, name, mult_args, mult_ret):
        self.auxiliaryFunctions[name] = Function(name, mult_args, mult_ret, "auxiliary")
        return self.auxiliaryFunctions[name]

    def addSetupFunction(self, name, mult_args, mult_ret):
        self.setupFunctions[name] = Function(name, mult_args, mult_ret, "setup")
        return self.setupFunctions[name]

    def addProcessingFunction(self, name, mult_args, mult_ret):
        self.processingFunctions[name] = Function(
            name, mult_args, mult_ret, "processing"
        )
        return self.processingFunctions[name]

    def getAllFunctions(self):
        retList = []
        for aux in self.auxiliaryFunctions:
            retList.append(self.auxiliaryFunctions[aux])
        for setup in self.setupFunctions:
            retList.append(self.setupFunctions[setup])
        for proc in self.processingFunctions:
            retList.append(self.processingFunctions[proc])
        return retList

    def getFunction(self, funcName):
        if funcName in self.auxiliaryFunctions:
            return self.auxiliaryFunctions[funcName]
        if funcName in self.setupFunctions:

            return self.setupFunctions[funcName]
        if funcName in self.processingFunctions:
            return self.processingFunctions[funcName]

    def initFunctions(self):
        return [
            func.name for func in self.getAllFunctions() if "INIT" in func.name.upper()
        ]

    def removeFunction(self, funcName):
        if funcName in self.initFunctions:
            del self.initFunctions[funcName]
        if funcName in self.auxiliaryFunctions:
            del self.auxiliaryFunctions[funcName]
        if funcName in self.setupFunctions:
            del self.setupFunctions[funcName]
        if funcName in self.processingFunctions:
            del self.processingFunctions[funcName]


"""Represents a sequence of function calls"""


class Sequence:
    def __init__(self):
        self.sequenceMembers = []
        self.variablesToInitialize = dict()
        self.hardCodedVariablesUsed = dict()
        self.functionsCalled = dict()
        self.functionCount = 0
        self.effectiveness = 0
        self.bitmap = set()
        self.cCode = None
        self.fuzzDataUsed = False
        self.functionPointerDeclarations = dict()
        self.func_targeted = False
        self.setupLen = None
        self.uninteresting_setup = False
        self.seedCov = dict()
        self.uses_size_arg = False

    """Update the dictionary for class function calls"""

    def updateVariablesToInitialize(self, updateDict):
        for var in updateDict:
            self.variablesToInitialize[var] = deepcopy(updateDict[var])

    """Create a new key for the function name"""

    def initializeDictionaryMember(self, currFunc):
        if currFunc not in self.variablesToInitialize:
            self.variablesToInitialize[currFunc] = []

    def add_aux_calls(self, aux_sequence):
        for info in aux_sequence:
            member, variables_to_initialize, hardcoded_values = info
            self.sequenceMembers.append(member)
            self.initializeDictionaryMember(member.name)
            for variable in variables_to_initialize:
                self.variablesToInitialize[member.name].append(variable)
            for value in hardcoded_values:
                self.hardCodedVariablesUsed[value[0]] = value

    def __str__(self):
        retstring = "Call Sequence: "
        for seqmem in self.sequenceMembers:
            retstring += str(seqmem)
        retstring += "\nVariables to initialize: " + str(self.variablesToInitialize)
        return retstring


"""Represents a single function call in a sequence"""


class SequenceMember:
    def __init__(self, name, args):
        self.name = name
        self.args = args
        self.checks = []

    def __str__(self):
        retstring = self.name + "("
        if len(self.args):
            for arg in self.args:
                retstring += arg.value + ", "
            retstring = retstring[:-2] + ")"
        else:
            retstring += ")"
        return retstring

    def __repr__(self):
        return str(self)


class literal_arg:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.value == other.value

    def __hash__(self):
        return hash(self.value)


class predefined_arg:
    def __init__(self, value):
        self.value = value


class define_new_val_arg:
    def __init__(self, value, definition, name):
        self.value = value
        self.definition = definition
        self.name = name

    def __eq__(self, other):
        if isinstance(other, define_new_val_arg):
            return self.definition == other.definition
        return False

    def __hash__(self):
        return hash(self.definition)


class multiplier_type:
    def __init__(self):
        self.base_type = None
        self.pointers = 0
        self.const = False
        self.consumes_fuzz = (False, None, None)
        self.internal_type = None
        self.explore_recurse = True  # small setting for self referential data types
        self.typedef_pointers = 0  # keeps track of underlying typedef pointers. ex: typedef obj* objp -- objp would have 1 underlying typedef pointer. This helps when setting struct properties

    def __str__(self):
        return f"base type: {self.base_type} pointers: {self.pointers} const: {self.const} consumes_fuzz: {self.consumes_fuzz} underlying pointers: {self.typedef_pointers}"


class function_pointer_arg:
    def __init__(self, value, definition):
        self.value = value
        self.definition = definition


class fuzz_buffer_arg:
    def __init__(self, type, value, argnum, void_cast):
        self.type = type
        self.value = value
        self.argnum = argnum
        self.void_cast = void_cast

    def __str__(self):
        return f"buf arg: {self.value} arg num: {self.argnum}"


class fuzz_struct_arg:
    def __init__(self, type, buf_props, size_props, argnum):
        self.type = type
        self.buf_props = buf_props
        self.size_props = size_props
        self.argnum = argnum

    def __str__(self):
        return f"struct art: buf props: {self.buf_props} len props: {self.size_props} argnum: {self.argnum}"


"""Static class that allows checking for compatibility of various types and functions"""


class CheckCompatibility:
    def __init__(
        self, index, mult_aliases, enums, target_func, track_params, allow_consts
    ):
        self.buffer_types = [
            "CHARACTER_S",
            "CHARACTER_U",
            "UINT",
            "VOID",
            "U_CHAR",
            "S_CHAR",
            "uintptr_t",
            "uint8_t",
            "Byte",
            "SHORT",
        ]
        self.index = index
        self.mult_aliases = mult_aliases
        self.enums = enums
        self.target_func = target_func
        self.track_params = track_params
        self.allow_consts = allow_consts
        self.initializeIntAlias()
        self.initializeCharAlias()
        self.type_map = {}
        self.map_types()
        self.clean_aliases()

    # avoids repetitive alias representations
    def clean_aliases(self):
        new_aliases = self.mult_aliases.copy()
        for alias in new_aliases:
            revised_list = set()
            name_mapping = set()
            for types in new_aliases[alias]:
                if not isinstance(types, str):
                    new_arg = multiplier_type()
                    self.init_mult_type(types, new_arg)
                    if (
                        new_arg.base_type != alias
                        and new_arg.base_type not in name_mapping
                    ):
                        name_mapping.add(new_arg.base_type)
                revised_list.add(types)
            new_aliases[alias] = revised_list
        self.mult_aliases.update(new_aliases)

    def map_types(self):
        lines = open(
            f"{pathlib.Path(os.path.realpath(__file__)).parent.parent}/extras/mult-to-c-types.txt",
            "r",
        ).readlines()
        for line in lines:
            split_line = line.split("=")
            self.type_map[split_line[0].strip()] = split_line[1].strip()

    def initializeIntAlias(self):
        if "INT" not in self.mult_aliases:
            self.mult_aliases["INT"] = set()
        intlist = ["U_INT", "INT128", "U_INT128", "U_INT"]
        for intval in intlist:
            self.mult_aliases["INT"].add(intval)
            if intval not in self.mult_aliases:
                self.mult_aliases[intval] = set(["INT"])
            else:
                self.mult_aliases[intval].add("INT")

        if "LONG" not in self.mult_aliases:
            self.mult_aliases["LONG"] = set()
        longlist = ["U_LONG", "uLongf", "uLong"]
        for longval in longlist:
            self.mult_aliases["LONG"].add(longval)
            if longval not in self.mult_aliases:
                self.mult_aliases[longval] = set(["LONG"])
            else:
                self.mult_aliases[longval].add("LONG")

    def initializeCharAlias(self):
        if "CHARACTER_S" not in self.mult_aliases:
            self.mult_aliases["CHARACTER_S"] = set()
        strlist = ["CHARACTER_U", "U_CHAR", "S_CHAR"]
        for strval in strlist:
            self.mult_aliases["CHARACTER_S"].add(strval)
            if strval not in self.mult_aliases:
                self.mult_aliases[strval] = set(["CHARACTER_S"])
            else:
                self.mult_aliases[strval].add("CHARACTER_S")

    def checkrets(self, functions):
        for func in functions:
            check = None
            if func.mult_ret.pointers:
                check = "isnot-null"
            elif func.mult_ret == "BOOL":
                check = "isnot-false"
            elif func.mult_ret == "VOID":
                check = "-"
            elif (
                self.check_builtin_type_compatibility(func.mult_ret, "INT", "dummy")
                or self.check_builtin_type_compatibility(func.mult_ret, "LONG", "dummy")
                or self.check_builtin_type_compatibility(
                    func.mult_ret, "size_t", "dummy"
                )
            ):
                check = "EXAMINE"
            else:
                check = "-"

            return f"{func.name}, {func.mult_ret.base_type + ('*' * func.mult_ret.pointers)}, {check}"

    def classify_function(self, api_functions, func):
        native_types = True
        argindex = 0
        fuzz_args = dict()
        consumes_buf = False
        mult_args = []
        mult_ret = multiplier_type()
        mult_ret = self.init_mult_type(func.mult_ret, mult_ret)
        for param in func.mult_args:
            mult_arg_obj = multiplier_type()
            mult_arg_obj = self.init_mult_type(param, mult_arg_obj)
            mult_args.append(mult_arg_obj)
            if mult_arg_obj.base_type not in self.type_map:
                native_types = False
            consumes_input, buf_props, size_props = mult_arg_obj.consumes_fuzz
            # only care about potentially setting string fields of structs when we're targeting a specific func
            if consumes_input:
                fuzz_arg = None
                if not buf_props:
                    consumes_buf = True
                    aliases = self.get_aliases(mult_arg_obj)
                    void_base = False
                    for a in aliases:
                        if type(a) is not str and a.base_type == "VOID":
                            void_base = True
                    fuzz_arg = fuzz_buffer_arg(
                        mult_arg_obj,
                        self.check_fuzz_compatible(mult_arg_obj).value,
                        argindex,
                        void_base,
                    )
                else:
                    fuzz_arg = fuzz_struct_arg(
                        mult_arg_obj, buf_props, size_props, argindex
                    )
                fuzz_args[argindex] = fuzz_arg
            argindex += 1

        if len(fuzz_args):
            if consumes_buf:
                setup_func = api_functions.addSetupFunction(
                    func.name, mult_args, mult_ret
                )
                setup_func.fuzz_args = fuzz_args
            else:
                proc_func = api_functions.addProcessingFunction(
                    func.name, mult_args, mult_ret
                )
                proc_func.fuzz_args = fuzz_args
            return
        if native_types:
            api_functions.addAuxiliaryFunction(func.name, mult_args, mult_ret)
            return
        api_functions.addProcessingFunction(func.name, mult_args, mult_ret)

    def determine_enum_status(self, enum_name):
        successKeywords = ["SUCCESS", "OK", "VALID", "SUCCEED"]
        failureKeywords = ["UNSUCCESS", "INVALID", "ERROR", "NOTOK", "FAIL", "NULL"]
        value = None
        currcomparison = None
        for val in self.enums[enum_name]:
            if any(x in val.upper() for x in successKeywords):
                if not any(x in val.upper() for x in failureKeywords):
                    return ("!=", val)
            # checking for enum values that contain failure keyword if no "successful" enum vals exist
            if any(x in val.upper() for x in failureKeywords):
                value = val
                currcomparison = "=="
        return currcomparison, value

    def determine_status_check(self, function):
        # status checks hold (operator, value)
        # loop through all arguments of a function. If all arguments are const we don't care about status checks.
        all_const_args = True
        arg_index = 0
        for arg in function.mult_args:
            if not arg.const:
                all_const_args = False
            arg_index += 1
        # determine if a status check on the returned value must be made
        if function.mult_ret.pointers:
            function.ret_status_check = ("!", None)
        elif self.check_builtin_type_compatibility(function.mult_ret, "BOOL", "dummy"):
            function.ret_status_check = (None, None)
        elif (
            self.check_builtin_type_compatibility(function.mult_ret, "INT", "dummy")
            or self.check_builtin_type_compatibility(function.mult_ret, "LONG", "dummy")
            or self.check_builtin_type_compatibility(
                function.mult_ret, "size_t", "dummy"
            )
        ) and not all_const_args:
            function.ret_status_check = ("<", "0")
        elif function.mult_ret.base_type in self.enums:
            if status := self.determine_enum_status(function.mult_ret.base_type):
                function.ret_status_check = status

    # Categorize and set status checks for each function
    def process_functions(self, api_functions, function_list, blacklist):
        for func in function_list:
            if func.name in blacklist:
                continue
            self.classify_function(api_functions, func)
        for function in api_functions.getAllFunctions():
            self.determine_status_check(function)
            if self.track_params:
                TrackCallSites.determine_potential_function_args(self.index, function)

    #  base_type, pointers, const, consumes_fuzz, internal_type
    def init_mult_type(self, curr_type, mult_type_obj):
        if isinstance(curr_type, mx.ast.BuiltinType):
            mult_type_obj.base_type = curr_type.builtin_kind.name
            mult_type_obj.consumes_fuzz = (
                mult_type_obj.base_type in self.buffer_types and mult_type_obj.pointers,
                None,
                None,
            )
            mult_type_obj.internal_type = curr_type
            return mult_type_obj
        # type has some sort of qualifier. unqualified_type field contains builtin type, pointer type, tagtype/typedef type
        elif isinstance(curr_type, mx.ast.QualifiedType):
            if curr_type.is_constant:
                mult_type_obj.const = True
            return self.init_mult_type(curr_type.unqualified_type, mult_type_obj)
        # pointer
        elif isinstance(curr_type, mx.ast.PointerType):
            mult_type_obj.pointers += 1
            return self.init_mult_type(curr_type.pointee_type, mult_type_obj)
        # enum/typedef/record type
        elif isinstance(curr_type, mx.ast.TagType) or isinstance(
            curr_type, mx.ast.TypedefType
        ):
            # we still want to do checking here to see if this type could potentially consume fuzzer generated data
            mult_type_obj.base_type = curr_type.declaration.name
            mult_type_obj.internal_type = curr_type
            if isinstance(curr_type.declaration, mx.ast.TypedefDecl):
                if mult_type_obj.explore_recurse:
                    new_mult_arg = multiplier_type()
                    new_mult_arg.explore_recurse = True
                    new_mult_arg = self.init_mult_type(
                        curr_type.declaration.underlying_type, new_mult_arg
                    )
                    if (
                        new_mult_arg.base_type in self.buffer_types
                        and mult_type_obj.pointers
                    ):
                        mult_type_obj.consumes_fuzz = (True, None, None)
                    elif new_mult_arg.consumes_fuzz[0]:
                        mult_type_obj.consumes_fuzz = new_mult_arg.consumes_fuzz
                    mult_type_obj.typedef_pointers = new_mult_arg.pointers
                    # update typedef mapping for cases where typedef is outside of included headers, probably a better way to do this in the future
                    self.update_aliases(
                        mult_type_obj.base_type, curr_type.declaration.underlying_type
                    )
                    return mult_type_obj
            elif isinstance(curr_type.declaration, mx.ast.RecordDecl):
                if curr_type.declaration.is_struct and mult_type_obj.explore_recurse:
                    buffer_field = []
                    size_field = []
                    for field in curr_type.declaration.fields:
                        new_mult_arg = multiplier_type()
                        new_mult_arg.explore_recurse = False
                        new_mult_arg = self.init_mult_type(field.type, new_mult_arg)
                        consumer, buf, size = new_mult_arg.consumes_fuzz
                        # don't want to consider structs that hold structs that could have data injected
                        if consumer and not buf and not size:
                            buffer_field.append((field.name, new_mult_arg))
                        elif self.check_builtin_type_compatibility(
                            new_mult_arg, "INT", "size"
                        ):
                            size_field.append((field.name, new_mult_arg))
                    if len(buffer_field):
                        mult_type_obj.consumes_fuzz = (True, buffer_field, size_field)
                        return mult_type_obj
                return mult_type_obj
            return mult_type_obj
        # tracing ParenType arg, commonly leads to inline function pointer parameter
        elif isinstance(curr_type, mx.ast.ParenType):
            return self.init_mult_type(curr_type.inner_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.AttributedType):
            return self.init_mult_type(curr_type.equivalent_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.UsingType):
            return self.init_mult_type(curr_type.underlying_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.ComplexType):
            # haven't tested handling this type yet
            return self.init_mult_type(curr_type.element_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.DeducedType):
            # haven't tested handling this type yet
            return self.init_mult_type(curr_type.resolved_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.MacroQualifiedType):
            # haven't tested handling this type yet
            return self.init_mult_type(curr_type.resolved_type, mult_type_obj)
        elif isinstance(curr_type, mx.ast.AdjustedType):
            # haven't tested handling this type yet
            return self.init_mult_type(curr_type.original_type, mult_type_obj)
        # function pointer - need an intermediate way to represent this is a function pointer
        elif isinstance(curr_type, mx.ast.FunctionProtoType):
            mult_type_obj.base_type = "function_pointer" + str(curr_type.__hash__())
            mult_type_obj.internal_type = curr_type
            return mult_type_obj
        # Haven't fully fleshed out dealing with arrays of fixed length
        elif isinstance(curr_type, mx.ast.ArrayType):
            if isinstance(curr_type, mx.ast.ConstantArrayType):
                mult_type_obj.const = True
            if curr_type.size_in_bits is None:
                mult_type_obj.pointers += 1
                return self.init_mult_type(curr_type.element_type, mult_type_obj)
            else:
                mult_type_obj.base_type = "unhandled arr" + str(curr_type.__hash__())
                mult_type_obj.internal_type = curr_type
                return mult_type_obj
        elif isinstance(curr_type, mx.ast.BlockPointerType):
            mult_type_obj.base_type = "unhandled block ptr" + str(curr_type.__hash__())
            mult_type_obj.internal_type = curr_type
            return mult_type_obj
        # c++ specific type, ignore
        elif isinstance(curr_type, mx.ast.LValueReferenceType) or isinstance(
            curr_type, mx.ast.RValueReferenceType
        ):
            mult_type_obj.base_type = "unhandled c++ type" + str(curr_type.__hash__())
            mult_type_obj.internal_type = curr_type
            return mult_type_obj
        elif isinstance(curr_type, mx.ast.ElaboratedType):
            return self.init_mult_type(curr_type.desugared_type, mult_type_obj)
        # catch-all to grab any other undefined type.
        elif isinstance(curr_type, mx.ast.Type):
            mult_type_obj.base_type = "unhandled type" + str(curr_type.__hash__())
            mult_type_obj.internal_type = curr_type
            print(f"Warning: unhandled type: {curr_type}")
            return mult_type_obj

    def resolve_type(self, curr_type):
        if curr_type.base_type in self.type_map:
            return self.type_map[curr_type.base_type] + "*" * curr_type.pointers
        else:
            return curr_type.base_type + "*" * curr_type.pointers

    # update any aliases to include typedefs found through init_mult_type
    def update_aliases(self, base_type, internal_type):
        if base_type in self.mult_aliases:
            if internal_type not in self.mult_aliases[base_type]:
                self.mult_aliases[base_type].add(internal_type)
        else:
            self.mult_aliases[base_type] = set()
            self.mult_aliases[base_type].add(internal_type)

    # return a list of either multiplier_arg or string
    def get_aliases(self, base_type):
        final_aliases = [base_type]
        alias_queue = []
        if isinstance(base_type, str):
            alias_queue.append(base_type)
        else:
            # multiplier_arg obj
            alias_queue.append(base_type.base_type)
        visited = []
        while len(alias_queue):
            curr_name = alias_queue.pop()
            if curr_name not in visited:
                visited.append(curr_name)
                if curr_name in self.mult_aliases:
                    for alias in self.mult_aliases[curr_name]:
                        if isinstance(alias, str):
                            final_aliases.append(alias)
                            alias_queue.append(alias)
                        else:
                            mult_arg_obj = multiplier_type()
                            mult_arg_obj.explore_recurse = False
                            mult_arg_obj = self.init_mult_type(alias, mult_arg_obj)
                            alias_queue.append(mult_arg_obj.base_type)
                            final_aliases.append(mult_arg_obj)
        return final_aliases

    def check_fuzz_compatible(self, type):
        type_aliases = self.get_aliases(type)
        for type_alias in type_aliases:
            if isinstance(type_alias, str):
                type_base, type_pointers = type_alias, 0
            else:
                type_base, type_pointers = (
                    type_alias.base_type,
                    type_alias.pointers,
                )
            if type_pointers:
                # if type compatible with character_s or is of type void*, compatible with
                for base_fuzz_type in self.buffer_types:
                    if self.check_builtin_type_compatibility(
                        type_alias, base_fuzz_type, "fuzzData"
                    ):
                        return predefined_arg("&" * (type_pointers - 1) + "fuzzData")
                    else:
                        extras = "&" * (type_pointers - 1)
                        if type_base == "VOID":
                            extras = "(void*)" + extras
                            return predefined_arg(extras + "fuzzData")

        return None

    def check_builtin_type_compatibility(self, dest, builtin_type, variable_name):
        dest_aliases = self.get_aliases(dest)
        builtin_aliases = self.get_aliases(builtin_type)
        for dest_val in dest_aliases:
            for builtin_val in builtin_aliases:
                dest_type_name = ""
                if isinstance(dest_val, str):
                    dest_type_name, dest_pointers = dest_val, 0
                else:
                    dest_type_name, dest_pointers = (
                        dest_val.base_type,
                        dest_val.pointers,
                    )
                if not isinstance(builtin_val, str):
                    builtin_val = builtin_val.base_type
                if dest_type_name == builtin_val:
                    if dest_pointers > 0:
                        return ("&" * dest_pointers) + variable_name
                    return variable_name
        return False

    def check_type_compatibility(self, dest, source, variable_name, function_arg):
        # keeps track of any dereferences or pointers that already exist
        # trying to figure out type of argument passed to previous function.
        # If the function contains a deref, we know the original type had one more pointer.
        # if it contains a ref, we know the original type is the # arg ptrs - 1
        refs = 0
        if variable_name.startswith("&"):
            refs = -1
        elif variable_name.startswith("*"):
            refs = variable_name.count("*")
        variable_name = (
            variable_name.replace("(void*)", "").replace("&", "").replace("*", "")
        )  # stripping any extra derefs/refs
        # if source is const, don't want to include it as a dependency
        if (not function_arg or not source.const) or self.allow_consts:
            # aliases are either to a mx.ast object or builtin type
            dest_aliases = self.get_aliases(dest)
            source_aliases = self.get_aliases(source)
            for dest_val in dest_aliases:
                for source_val in source_aliases:
                    dest_name = dest_val
                    source_name = source_val
                    if isinstance(dest_val, str):
                        dest_pointers = dest.pointers
                    else:
                        # changed from dest_val pointers to dest.pointers
                        dest_name, dest_pointers = (
                            dest_val.base_type,
                            dest.pointers,
                        )
                    if isinstance(source_val, str):
                        source_pointers = source.pointers
                    else:
                        source_name, source_pointers = (
                            source_val.base_type,
                            source.pointers,
                        )
                    if dest_name == source_name and len(dest_name) > 1:
                        add_void = (
                            "(void" + ("*" * dest_pointers) + ")"
                            if dest_name == "VOID"
                            else ""
                        )  # casting types to void * if needed
                        if dest_pointers > (source_pointers + refs):
                            # if the destination has more ptrs than the original type passed to the prev function, create a reference to the original type
                            return (
                                add_void
                                + "&" * (dest_pointers - (source_pointers + refs))
                                + variable_name
                            )
                        elif dest_pointers < (source_pointers + refs):
                            # if the original type passed into the function has more ptrs than the destination argument, dereference it.
                            return (
                                add_void
                                + "*" * ((source_pointers + refs) - dest_pointers)
                                + variable_name
                            )
                        return add_void + variable_name
        return False

    def check_function_compatibility(
        self, previous_function_args, dest, previous_function, previous_function_count
    ):
        # check return value:
        compatible_values = set()
        source = previous_function.mult_ret
        if decl := self.check_type_compatibility(
            dest, source, f"{previous_function.name}val{previous_function_count}", False
        ):
            compatible_values.add(decl)
        arg_counter = 0
        for param in previous_function.mult_args:
            if not isinstance(previous_function_args[arg_counter], literal_arg):
                decl = self.check_function_arg_compatibility(
                    param, dest, previous_function_args[arg_counter], False
                )
                if len(decl):
                    compatible_values.update(decl)
            arg_counter += 1
        return compatible_values

    def check_function_arg_compatibility(
        self, source, dest, variable_name, restrict_const
    ):
        compatible_values = set()
        # aliases are either to a mx.ast object or builtin type
        source_aliases = self.get_aliases(source)
        for alias in source_aliases:
            # looping through all aliases to account for case where pointer is aliased to non pointer
            if isinstance(alias, str):
                source_counter = 0
            else:
                source_counter = alias.pointers
            # arguments that can be passed between functions should be pointers
            if source_counter:
                if compatible := self.check_type_compatibility(
                    dest, source, variable_name, restrict_const
                ):
                    compatible_values.add(compatible)
        return compatible_values

    """Check if the type of an argument or return type are native to c"""

    def definedType(self, arg):
        return arg.base_type in self.type_map


"""Provides the functionality for converting a sequence to a C harness"""


class ConvertToC:
    def __init__(
        self,
        sequence,
        includes,
        hardcodedvars,
        functions,
        read_from_buffer,
        compatibility,
        add_define_to_harness,
    ):
        self.sequence = sequence
        self.includes = includes
        self.hardcodedvars = hardcodedvars
        self.functions = functions
        self.read_from_buffer = read_from_buffer
        self.file = C.cfile("program.c")
        self.compatibility = compatibility
        self.add_define_to_harness = add_define_to_harness
        self.type_to_val = {}
        self.map_type_to_val()

    def map_type_to_val(self):
        lines = open(
            f"{pathlib.Path(os.path.realpath(__file__)).parent.parent}/extras/type-to-val.txt",
            "r",
        ).readlines()
        for line in lines:
            split_line = line.split("=")
            self.type_to_val[split_line[0].strip()] = split_line[1].strip()

    """Driver for converting the sequence to a C file"""

    def Convert(self):
        self.write_includes()
        self.mainFunc()
        self.buildBody()
        return self.file

    """Adds the include statements to the file"""

    def write_includes(self):
        if self.add_define_to_harness:
            self.file.code.append(C.line(self.add_define_to_harness))

        for x in self.includes:
            self.file.code.append(C.line("#include " + x))
        self.file.code.append(C.blank())

    """adds the main function declaration to the file"""

    def mainFunc(self):
        # adding any function pointers that need to be declared
        for fp in self.sequence.functionPointerDeclarations:
            self.file.code.append(self.sequence.functionPointerDeclarations[fp])
        self.file.code.append(
            C.function(
                "main",
                "int",
            )
            .add_param(C.variable("argc", "int"))
            .add_param(C.variable("argv[]", "char", pointer=1))
        )

    """Builds the body within the main function. This is where the sequence of function calls occur"""

    def buildBody(self):
        funcDict = dict()
        body = C.block(innerIndent=3)
        for func in self.functions.getAllFunctions():
            funcDict[func.name] = 1
        if self.read_from_buffer:
            self.addReadFromBuffer(body)
        else:
            self.passFileArg(body)
        self.defineConstants(body)
        self.buildFuncVariables(body)
        for func in self.sequence.sequenceMembers:
            function = self.functions.getFunction(func.name)
            currCall = C.fcall(func.name)
            if "overload" in func.name:
                currCall = C.fcall(func.name[: func.name.index("overload")])
            argindex = 0
            for args in func.args:
                currVal = args.value
                currCall.add_arg(currVal)
                argindex += 1
            func2call = C.statement(currCall)
            func2statement = func2call.__str__()[:-1]
            name = ""
            if not self.compatibility.resolve_type(function.mult_ret) == "void":
                name = func.name + "val" + str(funcDict[func.name])
                funcDict[func.name] += 1
                type = self.compatibility.resolve_type(function.mult_ret)
                if isinstance(function.mult_ret.internal_type, mx.ast.RecordType):
                    type = "struct " + type
                varname = C.variable(name, type)
                func2statement = varname.__str__() + " = " + func2statement
            self.addArgChecks(
                body, func.args
            )  # adding pre-check for arguments that dereference a pointer
            self.addPrefixChecks(body, function, func.args)
            body.append(C.statement(func2statement))
            self.addChecks(body, function, name)
        body.append(C.statement("return 0"))
        self.file.code.append(body)

    def addArgChecks(self, body, args):
        argindex = 0
        for param in args:
            if (
                param.value.startswith("*") and not param.value == "NULL"
            ):  # dereferencing another pointer
                body.append(
                    f'\tif(!{param.value}){{\n\t\tfprintf(stderr, "err");\n\t\texit(0);\t}}'
                )  # adding a check to make sure dereferenced value is not NULL
            argindex += 1

    def addPrefixChecks(self, body, function, args):
        argindex = 0
        for arg in function.mult_args:
            if (not arg.const) and arg.pointers > 1:
                argument_param = args[argindex]
                if not isinstance(argument_param, predefined_arg):
                    continue
                name = args[argindex].value.strip("*").strip("&")
                if name == "NULL":
                    continue
                body.append(
                    f'\tif(!{name}){{\n\t\tfprintf(stderr, "err");\n\t\texit(0);\t}}'
                )
            argindex += 1

    def addChecks(self, body, function, name):
        operator, val = function.ret_status_check
        if operator == "no-check":
            return
        if not val:
            # accounting for if(!val) or simple if(val) case
            operator = operator if operator else ""
            body.append(
                f'\tif({operator}{name}){{\n\t\tfprintf(stderr, "err");\n\t\texit(0);\t}}'
            )
        else:
            variable_name = name
            if operator == "<":
                variable_name = "(int)" + variable_name
            body.append(
                f'\tif({variable_name} {operator} {val}){{\n\t\tfprintf(stderr, "err");\n\t\texit(0);\t}}'
            )

    """Defines the constant variables in the file """

    def defineConstants(self, body):
        for var in self.sequence.hardCodedVariablesUsed:
            h = self.sequence.hardCodedVariablesUsed[var]
            body.append(C.line(h[2] + " " + h[0] + " = " + h[1] + ";"))
        body.append("")

    """Declares and initializes the variables specifically defined for a function call"""

    def buildFuncVariables(self, body):
        variableList = self.sequence.variablesToInitialize
        for var in variableList:
            argCounter = 0
            for variable in variableList[var]:
                if variable[1] is None:
                    buffer_types = ["char*", "uint8_t*", "void*", "Bytef*"]
                    if any(buf in variable[0] for buf in buffer_types):
                        name = variable[2]
                        decl = f"{variable[0]} {name}[256];\n"  # If reading from filename, set a buffer size of 256
                        if self.read_from_buffer:
                            decl = f"{variable[0]} {name}[size+1];\n"  # If reading from buffer, set the size to size of read-in buffer
                        mem = f"\tsprintf({name}, \"/tmp/{str(''.join(random.choices(string.ascii_lowercase + string.digits, k=5)))}\");"
                        varInitialization = decl + mem
                    elif variable[0] not in self.type_to_val:
                        name = variable[2]
                        decl = f"{variable[0]} {name};\n"
                        mem = f"\tmemset(&{name}, 0, sizeof({name}));\n"
                        varInitialization = decl + mem
                    else:
                        if variable[0] == "void":
                            varInitialization = variable[0] + " " + variable[2] + ";"
                        else:
                            varInitialization = (
                                variable[0]
                                + " "
                                + variable[2]
                                + " = "
                                + self.getVal(variable[0])
                                + ";"
                            )
                    body.append(C.line(varInitialization))
                else:
                    varInitialization = variable[1]
                    body.append(C.line(varInitialization))
                argCounter += 1

    def addReadFromBuffer(self, body):
        body.append(
            """\tFILE *f;
    char *fuzzData = NULL;
    long size;

    if(argc < 2)
        exit(0);

    f = fopen(argv[1], "rb");
    if(f == NULL)
        exit(0);

    fseek(f, 0, SEEK_END);

    size = ftell(f);
    rewind(f);

    if(size < 1) 
        exit(0);

    fuzzData = (char*)malloc((size_t)size+1);
    if(fuzzData == NULL)
        exit(0);

    if(fread(fuzzData, (size_t)size, 1, f) != 1)
        exit(0);
    fuzzData[size] = \'\\0\';"""
        )

    def passFileArg(self, body):
        body.append("   char *fuzzData = argv[1];")

    """Returns a "dummy" value to set a variable to"""

    def getVal(self, arg):
        if arg in self.type_to_val:
            return self.type_to_val[arg]
        return "NULL"


class Dependency:
    def __init__(
        self,
        otherfunctionName,
        currFunctionIndex,
        otherFunctionIndex,
        objectName,
        funcName,
        typeCode,
    ):
        self.otherfunctionName = otherfunctionName
        self.currFunctionIndex = currFunctionIndex
        self.otherFunctionIndex = otherFunctionIndex
        self.objectName = objectName
        self.funcName = funcName
        self.typeCode = typeCode

    def __str__(self):
        return f"""Function Name: {self.otherfunctionName},Current Function's Argument #: {self.currFunctionIndex}, Other Function's Argument #: {self.otherFunctionIndex}, Class Object Name: {self.objectName}, Class Object Function: {self.funcName}, Dependency Code: {self.typeCode}"""


"""Provides the functionality for building the dependencies the algorithm is based on"""


class BuildDependencies:
    def __init__(self, functions, compatibility):
        self.functions = functions
        self.compatibility = compatibility

    def buildDependencies(self):
        self.buildAuxiliaryDependencies()
        self.buildSetupDependencies()
        self.buildProcessingDependencies()

    def buildAuxiliaryDependencies(self):
        for function in self.functions.auxiliaryFunctions:
            func = self.functions.auxiliaryFunctions[function]
            for posterior_func in self.functions.setupFunctions:
                posterior_func = self.functions.setupFunctions[posterior_func]
                self.addDependencies(func, posterior_func)
            for posterior_func in self.functions.processingFunctions:
                posterior_func = self.functions.processingFunctions[posterior_func]
                self.addDependencies(func, posterior_func)

    def buildSetupDependencies(self):
        for function in self.functions.setupFunctions:
            func = self.functions.setupFunctions[function]
            for posterior_func in self.functions.setupFunctions:
                posterior_func = self.functions.setupFunctions[posterior_func]
                if func.name != posterior_func.name:
                    self.addDependencies(func, posterior_func)
            for posterior_func in self.functions.processingFunctions:
                posterior_func = self.functions.processingFunctions[posterior_func]
                self.addDependencies(func, posterior_func)

    def buildProcessingDependencies(self):
        for function in self.functions.processingFunctions:
            func = self.functions.processingFunctions[function]
            for posterior_func in self.functions.processingFunctions:
                posterior_func = self.functions.processingFunctions[posterior_func]
                if func.name != posterior_func.name:
                    self.addDependencies(func, posterior_func)
            for posterior_func in self.functions.setupFunctions:
                posterior_func = self.functions.setupFunctions[posterior_func]
                self.addDependencies(func, posterior_func)

    def buildTargetDependencies(self, target_func):
        target_function = self.functions.getFunction(target_func)
        keep_functions = set()
        keep_functions.add(target_function.name)
        function_queue = [target_function]
        while len(function_queue):
            curr_func = function_queue.pop(0)
            for rev_dep in curr_func.reverseDependencies:
                if rev_dep.otherfunctionName not in keep_functions:
                    keep_functions.add(rev_dep.otherfunctionName)
                    function_queue.append(
                        self.functions.getFunction(rev_dep.otherfunctionName)
                    )

        function_queue = [target_function]
        while len(function_queue):
            curr_func = function_queue.pop(0)
            for dep in curr_func.dependencies:
                if dep.otherfunctionName not in keep_functions:
                    keep_functions.add(dep.otherfunctionName)
                    function_queue.append(
                        self.functions.getFunction(dep.otherfunctionName)
                    )
                    for rev_dep in self.functions.getFunction(
                        dep.otherfunctionName
                    ).reverseDependencies:
                        keep_functions.add(rev_dep.otherfunctionName)

        for func in self.functions.getAllFunctions():
            if func.name not in keep_functions and not func.category == "init":
                self.functions.removeFunction(func.name)
        return self.functions

    def addDependencies(self, func, posterior_func):
        # add both ways mean we add both a dependency and a reverse dependency for the given function.
        # We toggle this off to account for the rare case in which we want to call a processing function before a setup function while we're determining setup routines.
        addBothWays = True
        if posterior_func.category == "setup" and func.category == "processing":
            addBothWays = False
        post_arg_index = 0
        for post_arg in posterior_func.mult_args:
            if self.compatibility.check_type_compatibility(
                post_arg, func.mult_ret, "dummy", False
            ):
                if addBothWays:
                    func.addDependency(
                        Dependency(
                            posterior_func.name, post_arg_index, -1, None, None, 2
                        )
                    )
                posterior_func.addReverseDependency(
                    Dependency(func.name, -1, post_arg_index, None, None, 2)
                )
            arg_index = 0
            for arg in func.mult_args:
                if self.compatibility.check_function_arg_compatibility(
                    arg, post_arg, "dummy", True
                ):
                    if addBothWays:
                        func.addDependency(
                            Dependency(
                                posterior_func.name,
                                post_arg_index,
                                arg_index,
                                None,
                                None,
                                3,
                            )
                        )
                    posterior_func.addReverseDependency(
                        Dependency(func.name, arg_index, post_arg_index, None, None, 3)
                    )
                arg_index += 1
            post_arg_index += 1


class CompileHarness:
    def __init__(
        self,
        input_dir,
        output_dir,
        functions,
        hardcodedVars,
        includes,
        read_from_buffer,
        debug,
        compatibility,
        allow_stderr,
        target_func,
        execute_static_version,
        allow_lincov,
        add_define_to_harness,
    ):
        # constructor arguments
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.functions = functions
        self.hardcodedVars = hardcodedVars
        self.includes = includes
        self.read_from_buffer = read_from_buffer
        self.debug = debug
        self.compatibility = compatibility
        self.allow_stderr = allow_stderr
        self.target_func = target_func
        self.execute_static_version = execute_static_version
        self.allow_lincov = allow_lincov
        self.add_define_to_harness = add_define_to_harness

        # initializing other useful data
        self.successfulSequences = []
        self.routineSequences = []
        self.currIterSuccesses = (
            []
        )  # list to temporarily hold successful harnesses before they're optimized
        self.success = 0
        self.currIterSequences = {}
        self.failed = 0
        self.maxTuplesCaptured = 0
        self.globalBitmap = set()
        self.func_targets = 0
        self.targetSequences = []

        # stat tracking
        self.currTime = time.time()
        self.minute = 0
        self.totalFunctions = set()
        self.failedComp = 0
        self.failedCrash = 0
        self.failedCov = 0
        if debug:
            open(f"{self.output_dir}/debug-info/log_successful.txt", "w")
            open(f"{self.output_dir}/debug-info/log_failed.txt", "w")
            open(f"{self.output_dir}/debug-info/log_setup_routines.txt", "w")

    def checkSequence(self, sequence):
        newHarness = ConvertToC(
            sequence,
            self.includes,
            self.hardcodedVars,
            self.functions,
            self.read_from_buffer,
            self.compatibility,
            self.add_define_to_harness,
        )
        currentHarness = open(f"{self.output_dir}/gen/harness.c", "w")
        convertedHarness = str(newHarness.Convert())
        sequence.cCode = convertedHarness
        currentHarness.write(convertedHarness)
        currentHarness.close()

        # stat tracking
        newTime = time.time()
        if (newTime - self.currTime) / 60 > self.minute:
            statFile = open(f"{self.output_dir}/debug-info/log_stats", "a")
            statFile.write(
                f"{self.minute}, {self.success + self.failedComp + self.failedCov + self.failedCrash}, {self.success}, {self.failedComp}, {self.failedCov}, {self.failedCrash}, {len(self.globalBitmap)}, {len(self.totalFunctions)}\n"
            )
            statFile.close()
            self.minute += 1
        retval = self.compileHarness(sequence)
        return retval

    # there are some cases where the behavior of the library under test differs depending on if it is compiled statically or dynamically. This functionality just compiles the harness statically and checks if it crashes on any inputs
    def compileHarnessStatic(self, sequence):
        proc = subprocess.run(
            f"cd {self.input_dir} && OUT={self.output_dir}/gen make harness_static",
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            shell=True,
        )
        subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
        if not proc.returncode:
            seeds = os.listdir(f"{self.input_dir}/seeds_validcp")
            invalidSeeds = os.listdir(f"{self.input_dir}/seeds_invalidcp")
            for seed in seeds:
                try:
                    proc = subprocess.run(
                        f"cd {self.input_dir} && OUT={self.output_dir}/gen SEED={self.input_dir}/seeds_validcp/{seed} make showmap_static",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=True,
                        timeout=5,
                    )
                    subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
                    shutil.copytree(
                        f"{self.input_dir}/seeds_valid",
                        f"{self.input_dir}/seeds_validcp",
                        dirs_exist_ok=True,
                    )
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: crashed on file: {seed} err - {proc.stdout}\n",
                        )
                except UnicodeDecodeError:
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: crashed on file: {seed} err - {proc.stdout}\n",
                        )
                except subprocess.CalledProcessError:
                    # catch exception where we terminate OGHarn while a subprocess is running
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: process called error: {seed} err - {proc.stdout}\n",
                        )
                    continue
                except subprocess.TimeoutExpired:
                    self.failedCrash += 1
                    return 1, "Process timed out\n"
            for seed in invalidSeeds:
                try:
                    proc = subprocess.run(
                        f"cd {self.input_dir} && OUT={self.output_dir}/gen SEED={self.input_dir}/seeds_invalidcp/{seed} make showmap_static",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=True,
                        timeout=5,
                    )
                    subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
                    shutil.copytree(
                        f"{self.input_dir}/seeds_invalid",
                        f"{self.input_dir}/seeds_invalidcp",
                        dirs_exist_ok=True,
                    )
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: crashed on file: {seed} err- {proc.stdout}\n",
                        )
                except UnicodeDecodeError:
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: crashed on file: {seed} err - {proc.stdout}\n",
                        )
                    continue
                except subprocess.CalledProcessError:
                    # catch exception where we terminate OGHarn while a subprocess is running
                    if proc.returncode:
                        self.failedCrash += 1
                        return (
                            proc.returncode,
                            f"Static Execution: process called error: {seed} err - {proc.stdout}\n",
                        )
                    continue
                except subprocess.TimeoutExpired:
                    self.failedCrash += 1
                    return 1, "Process timed out\n"
            return 0, ""
        else:
            return 1, "Static Compilation: " + proc.stderr

    def compileHarness(self, sequence):
        if self.execute_static_version:
            exit_code, result = self.compileHarnessStatic(sequence)
            if exit_code:
                return result
        proc = subprocess.run(
            f"cd {self.input_dir} && OUT={self.output_dir}/gen make harness",
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            shell=True,
        )
        subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
        if not proc.returncode:
            totalBitmap = set()
            seeds = os.listdir(f"{self.input_dir}/seeds_validcp")
            invalidSeeds = os.listdir(f"{self.input_dir}/seeds_invalidcp")
            seedMaps = []
            unique_cov = False
            const_increase_amount = -1
            const_increase = True
            for seed in seeds:
                try:
                    proc = subprocess.run(
                        f"cd {self.input_dir} && OUT={self.output_dir}/gen SEED={self.input_dir}/seeds_validcp/{seed} make showmap",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=True,
                        timeout=5,
                    )
                    subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
                    shutil.copytree(
                        f"{self.input_dir}/seeds_valid",
                        f"{self.input_dir}/seeds_validcp",
                        dirs_exist_ok=True,
                    )
                    if proc.returncode:
                        self.failedCrash += 1
                        return f"crashed on file: {seed} err - {proc.stdout}\n"
                    if (not len(proc.stderr)) or self.allow_stderr:
                        currBitmap = self.getBitmap(
                            open(f"{self.output_dir}/gen/tempfile", "r")
                        )
                        # only need to check if we're gaining unique coverage if no other seed inputs have demonstrated that.
                        if seed in sequence.seedCov:
                            if const_increase_amount < 0:
                                const_increase_amount = len(
                                    currBitmap.difference(sequence.seedCov[seed])
                                )
                            if (
                                len(currBitmap.difference(sequence.seedCov[seed]))
                                != const_increase_amount
                            ):
                                const_increase = False
                        sequence.seedCov[seed] = currBitmap
                        if not unique_cov:
                            unique_cov = unique_cov or any(
                                [len(currBitmap ^ bmap) > 5 for bmap in seedMaps]
                            )
                            seedMaps.append(currBitmap)
                        totalBitmap = totalBitmap.union(currBitmap)
                except UnicodeDecodeError:
                    if proc.returncode:
                        self.failedCrash += 1
                        return f"crashed on file: {seed} err - {proc.stdout}\n"
                    # If the standard error spits out some random bytes a decoding exception can occur. If we don't care about the standard error then we leave this
                    if self.allow_stderr:
                        currBitmap = self.getBitmap(
                            open(f"{self.output_dir}/gen/tempfile", "r")
                        )
                        if seed in sequence.seedCov:
                            if const_increase_amount < 0:
                                const_increase_amount = len(
                                    currBitmap.difference(sequence.seedCov[seed])
                                )
                            if (
                                len(currBitmap.difference(sequence.seedCov[seed]))
                                != const_increase_amount
                            ):
                                const_increase = False
                        sequence.seedCov[seed] = currBitmap
                        if not unique_cov:
                            unique_cov = unique_cov or any(
                                [len(currBitmap ^ bmap) > 5 for bmap in seedMaps]
                            )
                            seedMaps.append(currBitmap)
                        totalBitmap = totalBitmap.union(currBitmap)
                    shutil.copytree(
                        f"{self.input_dir}/seeds_valid",
                        f"{self.input_dir}/seeds_validcp",
                        dirs_exist_ok=True,
                    )
                    continue
                except subprocess.CalledProcessError:
                    if proc.returncode:
                        self.failedCrash += 1
                        return f"crashed on file: {seed} err - {proc.stdout}\n"
                    # catch exception where we terminate OGHarn while a subprocess is running
                    continue
                except subprocess.TimeoutExpired:
                    self.failedCrash += 1
                    return "Process timed out\n"
            if not unique_cov and sequence.setupLen:
                self.failedCov += 1
                return "no unique coverage observed between seeds\n"
            if (const_increase and sequence.setupLen) and not self.allow_lincov:
                self.failedCov += 1
                return "constant coverage increase between seeds\n"
            uninteresting_cov = True
            for seed in invalidSeeds:
                try:
                    proc = subprocess.run(
                        f"cd {self.input_dir} && OUT={self.output_dir}/gen SEED={self.input_dir}/seeds_invalidcp/{seed} make showmap",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=True,
                        timeout=5,
                    )
                    subprocess.run(f"cd {os.getcwd()}", text=True, shell=True)
                    shutil.copytree(
                        f"{self.input_dir}/seeds_invalid",
                        f"{self.input_dir}/seeds_invalidcp",
                        dirs_exist_ok=True,
                    )
                    if proc.returncode:
                        self.failedCrash += 1
                        return f"crashed on file: {seed} err- {proc.stdout}\n"
                    currBitmap = self.getBitmap(
                        open(f"{self.output_dir}/gen/tempfile", "r")
                    )
                    if not len(totalBitmap.intersection(currBitmap)) == len(
                        totalBitmap
                    ):
                        uninteresting_cov = False
                except UnicodeDecodeError:
                    if proc.returncode:
                        self.failedCrash += 1
                        return f"crashed on file: {seed} err - {proc.stdout}\n"
                    shutil.copytree(
                        f"{self.input_dir}/seeds_invalid",
                        f"{self.input_dir}/seeds_invalidcp",
                        dirs_exist_ok=True,
                    )
                    continue
                except subprocess.CalledProcessError:
                    # catch exception where we terminate OGHarn while a subprocess is running
                    continue
                except subprocess.TimeoutExpired:
                    self.failedCrash += 1
                    return "Process timed out\n"
            if uninteresting_cov and "IGNORE_COV" not in os.environ:
                if sequence.setupLen:
                    self.failedCov += 1
                    return "invalid seeds offer no coverage difference\n"
            sequence.uninteresting_setup = uninteresting_cov or (not unique_cov)
            return totalBitmap
        else:
            self.failedComp += 1
            return proc.stderr

    def getBitmap(self, file):
        bmap = set()
        for line in file:
            bmap.add(line.split(":")[0])
        return bmap

    def updateFailedFiles(self, failure_message, cCode):
        self.failed += 1
        if self.debug:
            failedFiles = open(f"{self.output_dir}/debug-info/log_failed.txt", "a")
            failedFiles.write("File #" + str(self.failed) + "\n")
            failedFiles.write(failure_message)
            failedFiles.write(cCode + "\n")
            failedFiles.close()

    def updateSuccessfulFiles(self, effectiveness, cCode):
        successfulFiles = open(f"{self.output_dir}/debug-info/log_successful.txt", "a")
        successfulFiles.write(f"Unique Edges Captured: {str(effectiveness)}\n")
        successfulFiles.write(cCode + "\n")
        successfulFiles.close()

    def updateRoutineFiles(self, effectiveness, cCode):
        routineFile = open(f"{self.output_dir}/debug-info/log_setup_routines.txt", "a")
        routineFile.write("File #" + str(self.success) + "\n")
        routineFile.write(f"Unique Edges Captured: {str(effectiveness)}\n")
        routineFile.write(cCode + "\n")
        routineFile.close()

    def updateDebugLogs(self, localsequence):
        if localsequence.fuzzDataUsed:
            self.successfulSequences.append(localsequence)
            self.maxTuplesCaptured = max(
                self.maxTuplesCaptured, localsequence.effectiveness
            )
            self.success += 1
            if not self.target_func:
                sys.stdout.write(f"updated size of minimized corpus: {self.success}\r")
                sys.stdout.flush()
            elif localsequence.func_targeted:
                self.func_targets += 1
                sys.stdout.write(
                    f"updated size of minimized corpus that targets function: {self.success}\r"
                )
                sys.stdout.flush()
                self.targetSequences.append(localsequence)
            if self.debug:
                self.updateSuccessfulFiles(
                    localsequence.effectiveness, localsequence.cCode
                )
                self.updateTargetFiles(localsequence.effectiveness, localsequence.cCode)

    def finalizeRoutineLogs(self, localsequence):
        if localsequence.fuzzDataUsed:
            # self.routineSequences.append(localsequence)
            self.maxTuplesCaptured = max(
                self.maxTuplesCaptured, localsequence.effectiveness
            )
            self.success += 1
            if not self.target_func:
                sys.stdout.write(
                    f"minimized setup routine corpus size: {self.success} \r"
                )
                sys.stdout.flush()
            elif localsequence.func_targeted:
                self.func_targets += 1
                sys.stdout.write(
                    f"minimized setup routine with target corpus size: {self.func_targets} \r"
                )
                sys.stdout.flush()
                self.targetSequences.append(localsequence)
            if self.debug:
                self.updateRoutineFiles(
                    localsequence.effectiveness, localsequence.cCode
                )

    def updateRoutineLogs(self, localsequence):
        if localsequence.fuzzDataUsed:
            self.routineSequences.append(localsequence)
            self.maxTuplesCaptured = max(
                self.maxTuplesCaptured, localsequence.effectiveness
            )
            if not self.target_func:
                sys.stdout.write(
                    f"successful harnesses generated: {len(self.routineSequences)} \r"
                )
                sys.stdout.flush()
            elif localsequence.func_targeted:
                if localsequence.uninteresting_setup:
                    sys.stdout.write(
                        "Target does not gain interesting coverage, further exploration required\r"
                    )
                    sys.stdout.flush()
                else:
                    sys.stdout.write(
                        f"func successfully targeted {len(self.routineSequences)} time(s)\r"
                    )
                    sys.stdout.flush()
                    self.targetSequences.append(localsequence)
            if self.debug:
                self.updateRoutineFiles(
                    localsequence.effectiveness, localsequence.cCode
                )
                self.updateSuccessfulFiles(
                    localsequence.effectiveness, localsequence.cCode
                )
                self.updateTargetFiles(localsequence.effectiveness, localsequence.cCode)

    def updateTargetFiles(self, effectiveness, cCode):
        if self.targetSequences:
            successfulFiles = open(
                f"{self.output_dir}/debug-info/log_target_func.txt", "a"
            )
            successfulFiles.write(f"Unique Edges Captured: {str(effectiveness)}\n")
            successfulFiles.write(cCode + "\n")
            successfulFiles.close()

    def updateIterativeLogs(self, localsequence):
        if localsequence.fuzzDataUsed:
            self.maxTuplesCaptured = max(
                self.maxTuplesCaptured, localsequence.effectiveness
            )
            self.currIterSuccesses.append(localsequence)
            if not self.target_func:
                sys.stdout.write(
                    f"successful harnesses generated in current iteration: {len(self.currIterSuccesses)} \r"
                )
                sys.stdout.flush()
            elif localsequence.func_targeted:
                self.currIterSuccesses.append(localsequence)
                sys.stdout.write(
                    f"func successfully targeted in current iteration {len(self.currIterSuccesses)} time(s) \r"
                )
                sys.stdout.flush()

    def sumRoutineLog(self):
        if self.debug:
            routineFile = open(
                f"{self.output_dir}/debug-info/log_setup_routines.txt", "a"
            )
            routineFile.write(f"Max edges captured = {self.maxTuplesCaptured}")
            routineFile.close()


class TrackCallSites:
    @staticmethod
    def get_func_entity(index, func_name):
        for func in mx.ast.FunctionDecl.IN(index):
            if func.name == func_name:
                return func.id

    @staticmethod
    def trace_variable_operations(decl):
        ret_str = ""
        for ref in mx.Reference.to(decl):
            if stmt := ref.as_statement:
                for expr in mx.ast.Expr.containing(stmt):
                    if isinstance(expr, mx.ast.CompoundAssignOperator) or isinstance(
                        expr, mx.ast.BinaryOperator
                    ):
                        if isinstance(expr.lhs, mx.ast.DeclRefExpr):
                            if not expr.is_assignment_operation:
                                continue
                            if (
                                expr.opcode_string == "="
                            ):  # don't care about a straight-up assignment to a variable
                                continue
                            try:
                                lhs_name = expr.lhs.declaration.name
                                if (
                                    lhs_name == decl.name
                                    and expr.lhs.declaration.initializer
                                ):  # checking for initializer to avoid undefined behavior
                                    decl_type, data = TrackCallSites.parse_expr(
                                        expr.rhs, False
                                    )
                                    if decl_type == 1:
                                        expression = expr.tokens.data
                                        # sometimes the token can miss a semicolon
                                        if not expression.endswith(";"):
                                            expression += ";"
                                        ret_str += expression + "\n"
                            except Exception:
                                continue
                            # check if operation is being done on variable we care about
                        elif isinstance(expr.lhs, mx.ast.MemberExpr):
                            if isinstance(expr.lhs.base, mx.ast.DeclRefExpr):
                                try:
                                    lhs_name = expr.lhs.base.declaration.name
                                    if (
                                        lhs_name == decl.name
                                        and expr.lhs.base.declaration.initializer
                                    ):  # checking for initializer to avoid undefined behavior
                                        decl_type, data = TrackCallSites.parse_expr(
                                            expr.rhs, False
                                        )
                                        if decl_type == 1:
                                            expression = expr.tokens.data
                                            # sometimes the token can miss a semicolon
                                            if not expression.endswith(";"):
                                                expression += ";"
                                            ret_str += expression + "\n"
                                except Exception:
                                    continue
        return ret_str

    @staticmethod
    def track_variable_decl(var_arg, track_variable_operations):
        decl = var_arg.declaration
        if isinstance(decl, mx.ast.VarDecl):
            if decl.initializer:
                extra_operations = ""
                if track_variable_operations:
                    extra_operations = TrackCallSites.trace_variable_operations(decl)
                    if len(extra_operations):
                        extra_operations = "\n" + extra_operations
                decl_type, data = TrackCallSites.parse_expr(
                    decl.initializer, track_variable_operations
                )
                if decl_type == 1:
                    if not decl.initializer.tokens.data == "((void*)0)":
                        return 2, decl.tokens.data + extra_operations
        elif isinstance(decl, mx.ast.FunctionDecl):
            # function pointer arg
            return 3, decl.tokens.data
        elif isinstance(decl, mx.ast.EnumConstantDecl):
            # we already take care of the case of passing in enum vals
            return 1, None
        else:
            pass

        return None, None

    @staticmethod
    def track_member_expr(expr, track_variable_operations):
        if isinstance(expr.base, mx.ast.DeclRefExpr):
            arg_type, data = TrackCallSites.track_variable_decl(
                expr.base, track_variable_operations
            )
            if arg_type:
                return arg_type, data
        return None, None

    # return the type of argument and any corresponding data
    @staticmethod
    def parse_expr(expr, track_variable_operations):
        literal_types = [
            mx.ast.StringLiteral,
            mx.ast.IntegerLiteral,
            mx.ast.CompoundLiteralExpr,
            mx.ast.FixedPointLiteral,
            mx.ast.FloatingLiteral,
            mx.ast.ImaginaryLiteral,
            mx.ast.UserDefinedLiteral,
            mx.ast.CharacterLiteral,
        ]
        if type(expr) in literal_types:
            return 1, None
        elif isinstance(expr, mx.ast.ParenExpr):
            return TrackCallSites.parse_expr(
                expr.sub_expression, track_variable_operations
            )
        elif isinstance(expr, mx.ast.CastExpr):
            return TrackCallSites.parse_expr(
                expr.sub_expression, track_variable_operations
            )
        elif isinstance(expr, mx.ast.CallExpr):
            if expr.callee_declaration and expr.callee_declaration.name:
                return TrackCallSites.get_inline_call(expr, track_variable_operations)
            else:
                return 0, None
        elif isinstance(expr, mx.ast.DeclRefExpr):
            arg_type, definition = TrackCallSites.track_variable_decl(
                expr, track_variable_operations
            )
            if arg_type and arg_type > 1:
                return arg_type, definition
        elif isinstance(expr, mx.ast.MemberExpr):
            arg_type, definition = TrackCallSites.track_member_expr(
                expr, track_variable_operations
            )
            if arg_type:
                return arg_type, definition
        elif isinstance(expr, mx.ast.BinaryOperator):
            # probably could find a way to allow both rhs and lhs to be variables
            if (
                TrackCallSites.parse_expr(expr.lhs, track_variable_operations)[0] == 1
                and TrackCallSites.parse_expr(expr.rhs, track_variable_operations)[0]
                == 1
            ):
                return 1, None
        elif isinstance(expr, mx.ast.UnaryOperator):
            return TrackCallSites.parse_expr(
                expr.sub_expression, track_variable_operations
            )
        elif isinstance(expr, mx.ast.InitListExpr):
            # if all elements in list are literals then we consider it valid
            for init in expr.initializers:
                if (
                    not TrackCallSites.parse_expr(init, track_variable_operations)[0]
                    == 1
                ):
                    return None, None
            return 1, None
        elif isinstance(expr, mx.ast.ConditionalOperator):
            # can improve this to add both values as args if necessary
            if TrackCallSites.parse_expr(expr.lhs, track_variable_operations)[0] == 1:
                return 4, expr.lhs.tokens.data
            if TrackCallSites.parse_expr(expr.rhs, track_variable_operations)[0] == 1:
                return 4, expr.rhs.tokens.data
        elif isinstance(expr, mx.ast.ArraySubscriptExpr):
            # can add more here: index of arrays in struct property
            if TrackCallSites.parse_expr(expr.index, track_variable_operations)[0] == 1:
                return TrackCallSites.parse_expr(expr.base, track_variable_operations)
        elif isinstance(expr, mx.ast.UnaryExprOrTypeTraitExpr):
            if expr.keyword_kind.name == "SIZE_OF":
                return 4, f"sizeof({expr.type_of_argument.tokens.data})"
        else:
            pass
        return 0, None

    @staticmethod
    def get_arg_val(arg):
        if isinstance(arg, mx.ast.Expr):
            decl_type, data = TrackCallSites.parse_expr(arg, True)
            match decl_type:
                case 0:
                    return None
                case 1:
                    # ignore ((void*)0) since it's just a null pointer, which we already try
                    if not arg.tokens.data == "((void*)0)":
                        return literal_arg(arg.tokens.data)
                    return None
                case 2:
                    return define_new_val_arg(arg.tokens.data, data, None)
                case 3:
                    return function_pointer_arg(arg.tokens.data, data)
                case 4:
                    return literal_arg(data)

    # track a function call that's passed as a parameter to another function
    @staticmethod
    def get_inline_call(call_expr, track_variable_operations):
        all_literals = 1
        # making sure it's actually a call to the targeted function rather than being contained in another callExpr statement
        arg_index = 0
        for arg in call_expr.arguments:
            if not TrackCallSites.parse_expr(arg, track_variable_operations)[0] == 1:
                all_literals = 0
            arg_index += 1
        return (all_literals, None)

    @staticmethod
    def get_call_info(call_expr, function):
        # making sure it's actually a call to the targeted function rather than being contained in another callExpr statement
        func_name = function.name
        if "overload" in function.name:
            func_name = function.name[: function.name.index("overload")]
        if (
            call_expr.callee_declaration
            and call_expr.callee_declaration.name == func_name
        ):
            arg_index = 0
            for arg in call_expr.arguments:
                if arg_index < len(function.potential_arguments):
                    if call_site := TrackCallSites.get_arg_val(arg):
                        function.potential_arguments[arg_index].add(call_site)
                arg_index += 1

    @staticmethod
    def determine_potential_function_args(index, function):
        func_name = function.name
        if "overload" in function.name:
            func_name = function.name[: function.name.index("overload")]
        id = TrackCallSites.get_func_entity(index, func_name)
        if not id:
            return
        ent = index.entity(id)
        for call in ent.callers:
            TrackCallSites.get_call_info(call, function)
