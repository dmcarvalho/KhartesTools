import sys
import struct

BYNARY = True
FORMATED_TEXT = False

HEADER_SIZE_CONSTANT = 80


class StlWriter():
    def __init__(self, file_path, output_type=BYNARY):
        self.file_path = file_path
        self.output_type = output_type
        self.facets = 0
        try:
            self.file_obj = open(self.file_path, 'wb' if output_type else 'w')
        except:
            print "Unexpected error:", sys.exc_info()[0]
            raise
        self.first_line_writer()

    def first_line_writer(self):
        if self.output_type:
            # Write binary
            for i in range(HEADER_SIZE_CONSTANT):
                self.file_obj.write(struct.pack('c', ' '))
        else:
            self.file_obj.write("solid solid\n")

    def end_line_writer(self):
        if self.output_type:
            self.file_obj.seek(HEADER_SIZE_CONSTANT)
            self.file_obj.write(struct.pack('L', self.facets))
        else:
            self.file_obj.write("endsolid solid\n")

    def facet_writer(self, facets):
        dummy = 0
        
        if self.output_type:
            for v0, v1, v2, normal in facets:
                self.facets += 1
            # Write binary
                self.file_obj.write(struct.pack('f', normal[0]))
                self.file_obj.write(struct.pack('f', normal[1]))
                self.file_obj.write(struct.pack('f', normal[2]))
                self.file_obj.write(struct.pack('f', v0[0]))
                self.file_obj.write(struct.pack('f', v0[1]))
                self.file_obj.write(struct.pack('f', v0[2]))
                self.file_obj.write(struct.pack('f', v1[0]))
                self.file_obj.write(struct.pack('f', v1[1]))
                self.file_obj.write(struct.pack('f', v1[2]))
    
                self.file_obj.write(struct.pack('f', v2[0]))
                self.file_obj.write(struct.pack('f', v2[1]))
                self.file_obj.write(struct.pack('f', v2[2]))
                self.file_obj.write(struct.pack('h', dummy))

        else:
            for v0, v1, v2, normal in facets:
                self.facets += 1
                self.file_obj.write("  facet normal  %s  %s  %s\n" % (
                    str(normal[0]), str(normal[1]), str(normal[2])))
                self.file_obj.write("    outer loop\n")
                self.file_obj.write("      vertex  %s  %s  %s\n" %
                                    (str(v0[0]), str(v0[1]), str(v0[2])))
                self.file_obj.write("      vertex  %s  %s  %s\n" %
                                    (str(v1[0]), str(v1[1]), str(v1[2])))
                self.file_obj.write("      vertex  %s  %s  %s\n" %
                                    (str(v2[0]), str(v2[1]), str(v2[2])))
                self.file_obj.write("    endloop\n")
                self.file_obj.write("  endfacet\n")
