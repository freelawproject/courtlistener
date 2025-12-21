# Developer guides

Read these guides as needed:

1. Before starting, read our developer guide: https://github.com/freelawproject/courtlistener/wiki/Getting-Started-Developing-CourtListener/

The rules for code improvement and quality MUST be strictly followed by AI agents. For example, if it says that something "should" be done, that's guidance to humans. AIs MUST do those things.

1. To learn to do tests, read our testing guide: https://github.com/freelawproject/courtlistener/wiki/Automated-tests-on-CourtListener

1. To learn how to migrate the DB, read our DB guide: https://github.com/freelawproject/courtlistener/wiki/Database-migrations


# Coding Rules

1. NEVER write a URL into backend code. Only include them if strictly necessary in front end code. Instead, use django's tools for generating URLs.
1. New code MUST include type hints and must pass MyPy.
1. ALWAYS delete unused code that is created during a task.


# Testing

1. Try to keep the database between tests runs, for efficiency. 
1. If you need to run more than a few tests, just run them all.
1. Do not run the selenium tests unless necessary since they're very slow.
1. Use subTests if possible to create fewer test methods and classes.


# Submitting Work

1. When you make a plan, use the steps you took in the plan to break the changes into smaller commits, each with a particular unit of work. Use `git add -p` to do this at sub-file level where appropriate. For example, if the goal was to functions foo1() and bar1() in file1.py and update foo2() and bar2() in file2.py, you might want to commit the changes to foo functions in one commit and the changes to the bar functions in a second. 
1. Pull requests MUST be submitted as drafts and must use .github/PULL_REQUEST_TEMPLATE.md as their template.
1. Before submitting work, run pre-commit and ensure it passes.
1. Always update the branch before attempting to commit to it. Assume there are remote commits.


# Available tools

The application runs inside docker. Therefore:
 - You can run django commands with: `docker exec cl-django python manage.py XXX`

You have the following tools available on Linux machines:
 - grep is an alias to rg
 - gh
 - pre-commit
 - uv is available and is the only tool that should be used for dependencies
