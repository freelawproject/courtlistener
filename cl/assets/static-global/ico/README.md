Turns out that .ico files have a bit a of sophistication. For example, the one
you see here actually contains 9 images within it:

 - 16x16 @
    - 4bpp 1 bit alpha
    - 8bpp 1 bit alpha
    - 32bpp 8 bit alpha
 - 32x32 @
    - 4bpp 1 bit alpha
    - 8bpp 1 bit alpha
    - 32bpp 8 bit alpha
 - 48x48 @
     - 8bpp 1 bit alpha
     - 32bpp 8 bit alpha
 - 64x64 @
    - 8bpp 1 bit alpha
    - 32bpp 8 bit alpha

These can be pretty easily generated in Gimp by doing File > Import as Layers...
and then selecting all of the png files in this directory. From there, if you
export as .ico, it'll let you select how each layer should be handled. 

See: https://stackoverflow.com/questions/4354617/how-to-make-get-a-multi-size-ico-file
