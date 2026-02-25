This directory contains a .smali file used to generate a .dex file used
by libcore.java.lang.reflect.ParameterTest.

The use of .smali allows the generation of invalid system annotations
for parameter metadata that would be hard for a valid toolchain to
produce. For example,  invalid array lengths, null/empty parameter names.

Regenerate the .dex file with:

make smali
smali assemble libcore/luni/src/test/java/libcore/java/lang/reflect/parameter/MetadataVariations.smali \
    -o libcore/luni/src/test/resources/libcore/java/lang/reflect/parameter/metadata_variations.dex

---------------------

For reference, MetadataVariations started out as:

package libcore.java.lang.reflect.parameter;

public interface MetadataVariations {

    void emptyMethodParametersAnnotation();
    void tooManyAccessFlags(final String p0);
    void tooFewAccessFlags(final String p0, final String p1);
    void tooManyNames(final String p0);
    void tooFewNames(final String p0, final String p1);
    void tooManyBoth(final String p0);
    void tooFewBoth(final String p0, final String p1);
    void nullName(final String p0);
    void emptyName(final String p0);
    void nameWithSemicolon(final String p0);
    void nameWithSlash(final String p0);
    void nameWithPeriod(final String p0);
    void nameWithOpenSquareBracket(final String p0);
    void badAccessModifier(final String p0);
    void badlyFormedAnnotation(final String p0);

    void manyParameters(
            final int a000, final int a001, final int a002, final int a003, final int a004,
            final int a005, final int a006, final int a007, final int a008, final int a009,
            final int a010, final int a011, final int a012, final int a013, final int a014,
            final int a015, final int a016, final int a017, final int a018, final int a019,
            final int a020, final int a021, final int a022, final int a023, final int a024,
            final int a025, final int a026, final int a027, final int a028, final int a029,
            final int a030, final int a031, final int a032, final int a033, final int a034,
            final int a035, final int a036, final int a037, final int a038, final int a039,
            final int a040, final int a041, final int a042, final int a043, final int a044,
            final int a045, final int a046, final int a047, final int a048, final int a049,
            final int a050, final int a051, final int a052, final int a053, final int a054,
            final int a055, final int a056, final int a057, final int a058, final int a059,
            final int a060, final int a061, final int a062, final int a063, final int a064,
            final int a065, final int a066, final int a067, final int a068, final int a069,
            final int a070, final int a071, final int a072, final int a073, final int a074,
            final int a075, final int a076, final int a077, final int a078, final int a079,
            final int a080, final int a081, final int a082, final int a083, final int a084,
            final int a085, final int a086, final int a087, final int a088, final int a089,
            final int a090, final int a091, final int a092, final int a093, final int a094,
            final int a095, final int a096, final int a097, final int a098, final int a099,
            final int a100, final int a101, final int a102, final int a103, final int a104,
            final int a105, final int a106, final int a107, final int a108, final int a109,
            final int a110, final int a111, final int a112, final int a113, final int a114,
            final int a115, final int a116, final int a117, final int a118, final int a119,
            final int a120, final int a121, final int a122, final int a123, final int a124,
            final int a125, final int a126, final int a127, final int a128, final int a129,
            final int a130, final int a131, final int a132, final int a133, final int a134,
            final int a135, final int a136, final int a137, final int a138, final int a139,
            final int a140, final int a141, final int a142, final int a143, final int a144,
            final int a145, final int a146, final int a147, final int a148, final int a149,
            final int a150, final int a151, final int a152, final int a153, final int a154,
            final int a155, final int a156, final int a157, final int a158, final int a159,
            final int a160, final int a161, final int a162, final int a163, final int a164,
            final int a165, final int a166, final int a167, final int a168, final int a169,
            final int a170, final int a171, final int a172, final int a173, final int a174,
            final int a175, final int a176, final int a177, final int a178, final int a179,
            final int a180, final int a181, final int a182, final int a183, final int a184,
            final int a185, final int a186, final int a187, final int a188, final int a189,
            final int a190, final int a191, final int a192, final int a193, final int a194,
            final int a195, final int a196, final int a197, final int a198, final int a199,
            final int a200, final int a201, final int a202, final int a203, final int a204,
            final int a205, final int a206, final int a207, final int a208, final int a209,
            final int a210, final int a211, final int a212, final int a213, final int a214,
            final int a215, final int a216, final int a217, final int a218, final int a219,
            final int a220, final int a221, final int a222, final int a223, final int a224,
            final int a225, final int a226, final int a227, final int a228, final int a229,
            final int a230, final int a231, final int a232, final int a233, final int a234,
            final int a235, final int a236, final int a237, final int a238, final int a239,
            final int a240, final int a241, final int a242, final int a243, final int a244,
            final int a245, final int a246, final int a247, final int a248, final int a249,
            final int a250, final int a251, final int a252, final int a253, final int a254,
            final int a255, final int a256, final int a257, final int a258, final int a259,
            final int a260, final int a261, final int a262, final int a263, final int a264,
            final int a265, final int a266, final int a267, final int a268, final int a269,
            final int a270, final int a271, final int a272, final int a273, final int a274,
            final int a275, final int a276, final int a277, final int a278, final int a279,
            final int a280, final int a281, final int a282, final int a283, final int a284,
            final int a285, final int a286, final int a287, final int a288, final int a289,
            final int a290, final int a291, final int a292, final int a293, final int a294,
            final int a295, final int a296, final int a297, final int a298, final int a299
    );
}
