# Source for sameFieldNames.dex
.class public LsameFieldNames;
.super Ljava/lang/Object;
.implements Ljava/io/Serializable;

# Test multiple fields with the same name and different types.
# (Invalid in Java language but valid in bytecode.)
.field public a:J
.field public a:I
.field public a:Ljava/lang/Integer;
.field public a:Ljava/lang/Long;

.method public constructor <init>()V
    .registers 2
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method
