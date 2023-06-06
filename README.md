# CourtListener

Started [in 2009][me], CourtListener.com is the main initiative of [Free Law Project][flp]. The goal of CourtListener.com is to provide high quality legal data and services.

## What's Here

This repository is organized in the following way:

 - cl: the Django code for this project. 99% of everything is in this directory.
 - docker: Where to find compose files and docker files for various components.
 - scripts: logrotate, systemd, etc, and init scripts for our various configurations and daemons.


## Getting Involved

If you want to get involved send us an email with your contact info or take a look through the [issues list][issues]. There are innumerable things we need help with, but we especially are looking for help with:

 - legal research in order to fix data errors or other problems (check out the [data-quality label][dq] for some starting points)
 - fixing bugs and building features (most things are written in Python)
 - machine learning or natural language problems.
 - test writing -- we always need more and better tests

In general, we're looking for all kinds of help. Get in touch if you think you have skills we could use or if you have skills you want to learn by improving CourtListener.


## Contributing code

See the [developer guide][developing].


## Copyright

All materials in this repository are copyright Free Law Project under the Affero GPL. See LICENSE.txt for details.


## Contact

To contact Free Law Project, see here:

https://free.law/contact/


                       ````
                .:+oo++//++osso+/. -+++////+++.
             -+ys/-`         ./yy+  `./mmmm/``
           -sys:               `oo     ymmy
          +yyo`                 `+`    ymmy
         +yyy`                         ymms
        -yyy+                          ymms
        +yyy:                          ymms
        +sss:                          ymms
        /sss+                          ydds
        `ssss.                         sdds
         -syyo`                  ``    sdds
          .oyys-                `s/    ydds            `+`
            :shhs:`           `/ys`    yddh`          .hs
              .:oyys+:-....-/oyys.  `./ddddy/:--.---:odd.
                  `.-::///::-.`    -///////////////////-


[issues]: https://github.com/freelawproject/courtlistener/issues
[hw]: https://github.com/freelawproject/courtlistener/labels/help%20wanted
[dq]: https://github.com/freelawproject/courtlistener/labels/data-quality
[flp]: https://free.law/
[developing]: https://github.com/freelawproject/courtlistener/blob/main/DEVELOPING.md
[me]: https://github.com/freelawproject/courtlistener/commit/90db0eb433990a7fd5e8cbe5b0fffef5fbf8e4f6
