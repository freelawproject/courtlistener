The purpose of this `designs` folder is to provide an area for complex changes to be designed, reviewed, and accepted.

**When a design is probably not needed:**

If a proposed change will only affect one file or a small number of files in just one repository, then it may be faster to just create a branch, change those files, and do a pull request rather than create a design.

**When a design may be beneficial:**

Proposed changes that will affect multiple repositories or that have prompted a lot of discussion may be benefitted by the creation of:
- A branch, 
- A sub-folder within this `design` folder,
- A sub-folder `readme.md` file (a.k.a. the design document) and files with supporting details, and
- A pull request and pull-request comments about the design.

Designs should be oriented towards what is needed to gain approval.

Designs may benefit from having the following sections:
- Problem statement
- Proposed solution
  - Sub-sections for each component and a high-level description of what is being added, revised, and/or removed
  
Design documents are not likely to benefit from the inclusion of all code-level details because a design is just that:  a design.  It may be beneficial to do code-level changes in an entirely separate branch so the design review and acceptance can be completed prior to code-level reviews and acceptance.

**Proceeding from an accepted design to development:**

After a design is accepted, then it may be beneficial to create a single GitHub project in the core `courtlistener` repository.  The project can be used to identify and track tasks for the changes in all the repositories that the design says need to be changed.
