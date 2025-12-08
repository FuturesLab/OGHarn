import multiplier as mx
import engine


class Index_Target_Header:
    def __init__(self, db_path, headers, recurse):
        self.index = mx.Index.in_memory_cache(mx.Index.from_database(db_path))
        self.recurse = recurse
        self.headers = headers
        self.mx_headers = []
        self.valid_paths = set()
        self.functions = []
        self.enums = {}
        self.typedefs = {}
        self.fps = {}
        self.macros = []
        self.builtIns = []

        self.get_includes()

    def file_contained_in_headers(self, filename):
        for header in self.headers:
            if header in filename and filename.split("/")[-1] == header.split("/")[-1]:
                return True
        return False

    def get_includes(self):
        file_queue = []
        for file in self.index.files:
            filename = self.get_file_name(file)
            if self.file_contained_in_headers(filename):
                file_queue.append(file)

        # get the directory the header files are stored in
        if not len(file_queue):
            raise ValueError(
                "Indexed library does not contain files - The supplied .db file is likely malformed or incomplete."
            )

        base_paths = [
            "/".join(self.get_file_name(header_path).split("/")[:-2])
            for header_path in file_queue
        ]

        if self.recurse:
            # recursively pull in #included files,
            while len(file_queue):
                file = file_queue.pop(0)
                for reference in mx.frontend.IncludeLikeMacroDirective.IN(file):
                    referenced_filename = self.get_file_name(reference.included_file)
                    if any(
                        base_path in referenced_filename
                        and not self.file_contained_in_headers(referenced_filename)
                        for base_path in base_paths
                    ):
                        file_queue.append(reference.included_file)
                        self.headers.append(referenced_filename)

    def extractArtifacts(self):
        self.get_enums()
        self.get_macrodefs()
        self.get_typedefs()
        # function return type and arguments have both string representation and multiplier representation
        self.get_functions()
        return self.functions, self.macros, self.enums, self.fps, self.typedefs

    def get_func_info(self, func):
        return [p.original_type for p in func.parameters], func.return_type

    def get_file_name(self, file):
        for p in file.paths:
            return str(p)

    def contained_in_API_specific_header(self, entity):
        if file := mx.frontend.File.containing(entity):
            filename = self.get_file_name(file)
            return self.file_contained_in_headers(filename)
        return False

    def get_typedefs(self):
        for typeDef in mx.ast.TypedefDecl.IN(self.index):
            if not self.contained_in_API_specific_header(typeDef):
                continue
            if isinstance(typeDef.underlying_type, mx.ast.ElaboratedType):
                if isinstance(typeDef.underlying_type.named_type, mx.ast.EnumType):
                    self.add_enum(
                        typeDef.underlying_type.named_type.declaration, typeDef.name
                    )
                continue
            # function pointers are declared as pointer types and then FunctionProtoType types
            if isinstance(typeDef.underlying_type, mx.ast.PointerType) and isinstance(
                typeDef.underlying_type.pointee_type, mx.ast.FunctionProtoType
            ):
                self.fps[typeDef.name] = typeDef.underlying_type.pointee_type
            elif typeDef.name in self.typedefs:
                self.typedefs[typeDef.name].add(typeDef.underlying_type)
            else:
                self.typedefs[typeDef.name] = set()
                self.typedefs[typeDef.name].add(typeDef.underlying_type)

    def get_macrodefs(self):
        for macro in mx.frontend.DefineMacroDirective.IN(self.index):
            if not self.contained_in_API_specific_header(macro):
                continue
            if macro.is_function_like:
                # don't really care about function-like macros for now
                continue
            self.macros.append(macro.name.data)

    def get_functions(self):
        func_occurrences = {}
        func_mapping = {}
        for func in mx.ast.FunctionDecl.IN(self.index):
            if not self.contained_in_API_specific_header(func):
                continue
            mult_args, mult_ret = self.get_func_info(func)
            func_name = func.name
            if func.name in func_mapping:
                if not any(x == mult_args for x in func_mapping[func.name]):
                    # storing overloaded functions if necessary
                    func_name = f"{func.name}overload{func_occurrences[func.name]}"
                    func_occurrences[func.name] += 1
                    func_mapping[func.name].append(mult_args)
                    self.functions.append(
                        engine.Function(func_name, mult_args, mult_ret)
                    )
            else:
                func_mapping[func.name] = [mult_args]
                func_occurrences[func.name] = 1
                self.functions.append(engine.Function(func_name, mult_args, mult_ret))

    def add_enum(self, enum, name):
        if not self.contained_in_API_specific_header(enum):
            return
        self.enums[name] = []
        for val in enum.enumerators:
            self.enums[name].append(val.name)

    def get_enums(self):
        for enum in mx.ast.EnumDecl.IN(self.index):
            if enum.name:
                self.add_enum(enum, enum.name)
            elif enum.typedef_name_for_anonymous_declaration:
                self.add_enum(enum, enum.typedef_name_for_anonymous_declaration.name)
