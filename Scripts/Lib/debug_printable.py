from pprint import pformat

class DebugPrintable:
    recursion_limit_stack = set()
    def __repr__(self):
        if (self in self.recursion_limit_stack):
            return f"<0x{id(self):012x}>"
        else:
            self.recursion_limit_stack.add(self)
            formatted = pformat(vars(self))
            self.recursion_limit_stack.remove(self)
            return formatted