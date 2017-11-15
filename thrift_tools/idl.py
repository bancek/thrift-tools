import os

from ptsd.parser import Parser
from ptsd import ast

class Type(object):
    def parse(self, value):
        pass

class TypeDef(object):
    def __init__(self, name, type):
        self.name = name
        self.type = type

class Enum(Type):
    def __init__(self, name, values):
        self.name = name
        self.values = values
        self.names_by_tags = dict((value, name) for (name, value) in self.values)

    def parse(self, value):
        return self.names_by_tags[value]

class Field(object):
    def __init__(self, tag, name, is_required, type):
        self.tag = tag
        self.name = name
        self.is_required = is_required
        self.type = type

class Struct(Type):
    def __init__(self, name, fields):
        self.name = name
        self.fields = fields
        self.fields_by_tags = dict((x.tag, x) for x in self.fields)

    def parse(self, fields):
        struct_fields = []

        fields_by_tag = dict((x.field_id, x) for x in fields)

        for field_def in self.fields:
            value = None

            field = fields_by_tag.get(field_def.tag)

            if field is not None:
                value = field.value

                if isinstance(field_def.type, Type):
                    value = field_def.type.parse(value)

            struct_fields.append((field_def.name, value))

        return (self.name, struct_fields)

class Exc(Struct):
    pass

class List(Type):
    def __init__(self, type):
        self.type = type

    def parse(self, values):
        list_values = []

        for value in values:
            if isinstance(self.type, Type):
                value = self.type.parse(value)

            list_values.append(value)

        return list_values

class Set(Type):
    def __init__(self, type):
        self.type = type

    def parse(self, values):
        set_values = set()

        for value in values:
            if isinstance(self.type, Type):
                value = self.type.parse(value)

            set_values.add(value)

        return set_values

class Map(Type):
    def __init__(self, key_type, value_type):
        self.key_type = key_type
        self.value_type = value_type

    def parse(self, map):
        map_values = {}

        for key, value in map:
            if isinstance(self.key_type, Type):
                key = self.key_type.parse(key)
            if isinstance(self.value_type, Type):
                value = self.value_type.parse(value)

            map_values[key] = value

        return map_values

class Function(object):
    def __init__(self, name, arguments, type, throws):
        self.name = name
        self.arguments = arguments
        self.arguments_by_tags = dict((x.tag, x) for x in self.arguments)
        self.type = type
        self.throws = throws
        self.throws_by_tags = dict((x.tag, x) for x in self.throws)

    def get_args(self, msg):
        try:
            if msg.type == 'call':
                args = []

                args_by_tag = dict((x.field_id, x) for x in msg.args)

                for arg in self.arguments:
                    value = args_by_tag.get(arg.tag).value

                    if isinstance(arg.type, Type):
                        value = arg.type.parse(value)

                    args.append((arg.name, value))

                return args
            elif msg.type == 'reply':
                if len(msg.args) > 0:
                    if msg.args[0].field_id == 0: # return
                        value = msg.args[0].value

                        if isinstance(self.type, Type):
                            value = self.type.parse(value)

                        return value
                    else: # throws
                        value = msg.args[0].value
                        throw_type = self.throws_by_tags[msg.args[0].field_id].type

                        if isinstance(throw_type, Type):
                            value = throw_type.parse(value)

                        return value
        except:
            import traceback
            traceback.print_exc()

        return msg.args

class Idl(object):
    def __init__(self, functions):
        self.functions = functions
        self.functions_by_name = dict((x.name, x) for x in self.functions)

    def get_function(self, name):
        return self.functions_by_name.get(name, None)

def parse_idl_file(path):
    functions = []
    types_by_name = {}

    def resolve_type(type):
        if isinstance(type, ast.Identifier):
            resolved_type = types_by_name[type.value]

            if isinstance(resolved_type, TypeDef):
                return resolve_type(resolved_type.type)

            return resolved_type
        elif isinstance(type, ast.List):
            return List(
                type = resolve_type(type.value_type),
            )
        elif isinstance(type, ast.Set):
            return Set(
                type = resolve_type(type.value_type),
            )
        elif isinstance(type, ast.Map):
            return Map(
                key_type = resolve_type(type.key_type),
                value_type = resolve_type(type.value_type),
            )
        else:
            return type

    def parse_body(body):
        for body_part in body:
            if isinstance(body_part, ast.Typedef):
                typedef = TypeDef(
                    name = body_part.name.value,
                    type = resolve_type(body_part.type),
                )

                types_by_name[typedef.name] = typedef

            elif isinstance(body_part, ast.Enum):
                values = [(x.name.value, x.tag) for x in body_part.values]

                enum = Enum(
                    name = body_part.name.value,
                    values = values,
                )

                types_by_name[enum.name] = enum

            elif isinstance(body_part, ast.Struct):
                fields = []

                for field_ast in body_part.fields:
                    field = Field(
                        tag = field_ast.tag,
                        name = field_ast.name.value,
                        is_required = field_ast.required,
                        type = resolve_type(field_ast.type)
                    )

                    fields.append(field)

                struct = Struct(
                    name = body_part.name.value,
                    fields = fields,
                )

                types_by_name[struct.name] = struct

            elif isinstance(body_part, ast.Exception_):
                fields = []

                for field_ast in body_part.fields:
                    field = Field(
                        tag = field_ast.tag,
                        name = field_ast.name.value,
                        is_required = field_ast.required,
                        type = resolve_type(field_ast.type)
                    )

                    fields.append(field)

                exc = Exc(
                    name = body_part.name.value,
                    fields = fields,
                )

                types_by_name[exc.name] = exc

            elif isinstance(body_part, ast.Service):
                for function_ast in body_part.functions:
                    arguments = []

                    for argument_ast in function_ast.arguments:
                        argument = Field(
                            tag = argument_ast.tag,
                            name = argument_ast.name.value,
                            is_required = True,
                            type = resolve_type(argument_ast.type),
                        )

                        arguments.append(argument)

                    throws = []

                    for throw_ast in function_ast.throws:
                        throw = Field(
                            tag = throw_ast.tag,
                            name = throw_ast.name.value,
                            is_required = False,
                            type = resolve_type(throw_ast.type),
                        )

                        throws.append(throw)

                    function = Function(
                        name = function_ast.name.value,
                        arguments = arguments,
                        type = resolve_type(function_ast.type),
                        throws = throws,
                    )

                    functions.append(function)

    def parse_file(path):
        with open(path) as fp:
            tree = Parser().parse(fp.read())

        for include in tree.includes:
            include_path = os.path.join(os.path.dirname(path), include.path.value)

            parse_file(include_path)

        parse_body(tree.body)

    parse_file(path)

    return Idl(
        functions = functions,
    )

if __name__ == '__main__':
    print parse_idl_file('thrift_tools/tests/resources/tutorial.thrift').functions
