# Developing CourtListener

CourtListener is built upon a few key pieces of technology that need to come together. Whether you're contributing platform code, web design, etc. it helps to know the easiest ways to run and test the project.

Historically, we have used [wiki instructions to get set up][wiki], but these days most things can be accomplished using docker.

But before we can get into that, we must address...


## Legal Matters

Not surprisingly, we have a lot of legal, and, in particular, intellectual property, lawyers around here. As a result, we endeavor to be a model for other open source projects in how we handle IP contributions and concerns.

We do this in a couple of ways. First, we use a copy-left license for CourtListener, the GNU GPL Affero license. Read the details in the license itself, but the high level is that it's a copy-left license that's designed specifically for the kind of code that's run on servers and isn't distributed to end users (like an app would be, say).

The other thing we do is require a contributor license agreement from any non-employees or non-contractors that contribute code to the project. The first time you make a contribution to any of our repos, a bot will ask you sign the agreement. Please do so. If you have any questions about it, please ask.

On with the show.


# Discussing things

You can use [Github Discussions][ghd] to ask questions and search past ones. We should use this more, but mostly people seem to get into our Slack and ask things there. When they do that, the answers to their questions go into a black hole and only ever help the person that asked them. Ah well.


## Architecture

The major components of CourtListener are:

 - Postgresql - For database storage. We used to use MySQL long ago, but it caused endless weird and surprising problems. Postgresql is great.

 - Redis - For in-memory fast storage, caching, task queueing, some stats logging, etc. Everybody loves Redis for a reason. It's great. If you have something small you want to store quickly and kind of durably, it's fantastic.

 - Celery - For running asynchronous tasks. We've been using this a long time. It causes a lot of annoyance and sometimes will have unsolvable bugs, but as of 2019 it's better than any of the competition that we've tried.

 - Judge Pics and Court Seals microservices - These are services we host via S3. They're not complicated. They just give you a photo of a judge or a seal at a given URL.

 - [Doctor][dr] - This is our microservice for document and audio file conversions. Inside the service we do text extraction, OCR (using tesseract), mp3 enhancements, etc.

 - Solr - For making things searchable. It's *decent*. Our version is currently very old, but it hangs in there. We've also tried Sphinx. Lately, we've been moving towards Elastic.

 - React - For dynamic front-end features. We're slowly moving the trickiest parts of the front end over to React.

 - Python/Django/et al - And their associated bits and pieces.


### Developer Installation

We use a Docker Compose file to make development easier. Don't use it for production! It's not secure enough, and it uses bad practices for data storage. But if you're a dev, it should work nicely.

Below is the process for getting everything working. If you get stuck, note that we run all tests in GitHub Actions and that there is a complete, automated setup script in `tests.yml` that you can consult.

To set up a development machine, do the following:

1. Clone the [courtlistener](https://github.com/freelawproject/courtlistener) and [courtlistener-solr-server](https://github.com/freelawproject/courtlistener-solr-server) repositories so that they are side-by-side in the same folder.

1. Install the React dependencies and get hot-reloading going. Install node, and then `cd` into courtlistener/cl and run:

    ```bash
    npm install
    npm run dev
    ```

1. Next, you'll need to update the group permissions for the Solr server. `cd` into the courtlistener-solr-server directory, and run the following commands:

    ```bash
    sudo chown -R :1024 data
    sudo chown -R :1024 solr
    sudo find data -type d -exec chmod g+s {} \;
    sudo find solr -type d -exec chmod g+s {} \;
    sudo find data -type d -exec chmod 775 {} \;
    sudo find solr -type d -exec chmod 775 {} \;
    sudo find data -type f -exec chmod 664 {} \;
    sudo find solr -type f -exec chmod 664 {} \;
    ```

1. Create a personal settings file. To do that, copy-paste the `.env.example` file to `.env.dev`, and then minimally uncomment these settings:

    - `ALLOWED_HOSTS`: This is needed so tests can pass. You can set it to `localhost` for more security, or set it to `*` if you're on a safe LAN.
    - `SECRET_KEY`: This is a django setting that salts encryption algorithms, among other things. Just set it to something random, if you like.

    That will get you pretty far, but CourtListener does rely on a number of cloud services, as you'll see in the `env.example` file. To make all features work, you'll need to get tokens for these services.

    See [below](#how-settings-work-in-courtlistener) for more information about settings files.

1. Next, create the bridge network that docker relies on:

    `docker network create -d bridge --attachable cl_net_overlay`

    This is important so that each service in the compose file can have a hostname.

1. `cd` into courtlistener/docker/courtlistener, then launch the server by running:

    `docker-compose up`

    *Docker Desktop for Mac users:* By default, Docker runs with very little memory (2GB), so to run everything properly you will need to change the default values:

      - Go to docker Settings/Resources/Advanced
      - Increase Memory to at least 4GB and Swap to 2GB
      - Apply changes and Restart.

1. Generate some dummy data for your database:

        docker exec -it cl-django python /opt/courtlistener/manage.py make_dev_data

    If this does not make an object that you want for your work, you should update it so it does. It's a relatively new tool and it's growing as we use it.

    If you need specific data from CourtListener (to debug something, say), you can use `clone_from_cl`, which pulls data from the CourtListener API into your dev database.

1. Finally, create a new superuser login by running this command, and entering the required information:

    `docker exec -it cl-django python /opt/courtlistener/manage.py createsuperuser`

*Speed Tip:* If you want your tests and docker images to go faster, you might be able to run:

    `docker-compose -f docker-compose.yml -f docker-compose.tmpfs.yml up

*M1 Mac/ARM Tip:* If you are running tests on Apple silicon you may need to change the selenium image to `image: seleniarm/standalone-chromium:latest` to properly run the tests.

If you do that, you'll run postgresql in memory. That means it'll get wiped out whenever you restart docker, but it should provide a speed bump. We do this in CI, for example.

So that should be it! You should now be able to access the following URLs:

 - <http://127.0.0.1:8000> - Your dev homepage
 - <http://127.0.0.1:8000/admin> - The Django admin page (try the super user)
 - <http://127.0.0.1:8983/solr> - Solr admin page
 - 127.0.0.1:5900 - A VNC server to the selenium machine (it doesn't serve http though)

A good next step is to [run the test suite](#testing) to verify that your development server is configured correctly.

[cl-solr]: https://github.com/freelawproject/courtlistener-solr-server

### Problem Solving

1. **It seems like dependencies are missing when I start docker.**

Sometimes the code is ahead of the images that you pulled from docker hub because we haven't deployed the code in `main` yet. If so, build a fresh docker image for yourself with:

    make development --file docker/django/Makefile

Then run something like `docker restart cl-django` and you should be good, or if that fails, just restart the whole compose file.

2. Add your problem here...


## Ongoing code upgrades you should do when possible

Python and its ecosystem are always evolving. There are a number of best practices that we do to try to keep up:

1. We are gradually adding type hints to our code. It's too difficult to do this all at once, so all new code should be hinted. If you have time while in a file, you should add hints where you can. It may help to enable an error in your IDE for unhinted code.

    After you've added hints, you should add the file or the module to the list of supported modules in lint.yml. A great pull request will add a file or module to lint.yml.

1. We no longer use django fixtures in tests. They are slow and confusing and should be removed when you see them. Instead, they should be replaced with `setupTestData()` and factories. Search the code for examples. New fixtures should be strictly avoided.

1. Wherever possible, we should use `Pathlib` instead of `os.path` and friends. It's almost always nicer, and it's worth learning and using it.


## Logs

You can see most of the logs via docker when you start it. CourtListener also keeps a log in the `cl-django` image that you can tail with:

    docker exec -it cl-django tail -f /var/log/courtlistener/django.log

But usually you won't need to look at these logs.

Logs in production are currently only available to a few people, but once we move to Kubernetes, they'll be available to all.


## How Settings Work in CourtListener

CourtListener has two kinds of settings: Those that can and should be adjusted by end users and those that are the same for everybody. Ones that can be adjusted have sane, safe defaults that can be overridden by environment variables. Ones that should not be overridden are simply hardcoded until somebody makes the case that they should be adjustable.

For developers (it's different in prod), adjustable settings are configured via a file located at `.env.dev`. Variables set in that file are picked up via the docker compose file or a kubernetes manifest, which passes them to the docker image running your code. Finally, our django code uses [django-environ][env] to pick up and use those variables.

All defaults — for adjustable and fixed settings alike — can be found in the `cl/settings` directory, where they are organized into a few categories of settings (third-party vs. first-party, django, and misc).

This design comports with [factor three][3] of the 12-factor app guidelines.


## Guidelines for Contributions

For the most part, we use [Github flow][flow] to get our work done. Our
[BDFL][bdfl] and primary developer is [@mlissner][me]. For better and/or for worse,
he doesn't care too much about git, provided things get done smoothly and his
life is fairly easy. What that means generally, is:

1. Commits should represent a unit of work. In other words, if you're working
on a big feature, each commit should be a discrete step along the path of
getting that feature ready to land. Bad or experimental work shouldn't be in a
commit that you submit as part of a PR, if you can avoid it. Often you can clean up your commits with an interactive rebase followed by a force push to your branch.

2. After a code review has begun, **do not force push**. If you do, it makes it difficult for the next review to identify your latest changes. It's better to have a messy commit log during review than to force your poor reviewer to look at the entire PR again just to see the one or two lines you changed. After the review is completed, a force push might be used to clean things up, but a squash merge might do it too, and those are easy.

3. Your commit messages should use [the format defined by the Angular.js
project][format]. This is pretty easy if you use [this plugin][format-plugin]
for Intellij/PyCharm/et al.

    Your commits should therefore look something like:

        fix(component): Makes the whatsit do the thingsit

        Some longer explanation might go here, explaining why the whatsit is
        broken and how you fixed it.

        Fixes: #xyz

    We welcome LONG commit messages that could literally double as blog posts. If somebody is looking at the commit in five years, they *want* an essay, not a tweet.

1. PR's that do anything visual (email templates, HTML pages, etc) should include a comment with a screenshot or gif of the visual changes.

1. *KEEP YOUR PR's SMALL*. A good PR should land a specific thing of some sort.
It doesn't have to be done — it doesn't even have to work! — but it should be
clean, and it should be your best effort at clean *progress*. PRs are both a way
of getting your work into the system and a way to *communicate* your work. The
latter is more important. 10 small, clean PRs are about 50× better than a
monolithic one that is fully functional.

    Say you are developing a system that relies on regexes to do something. Why
    not submit the regexes (and their tests!) in one PR and the thing that uses
    those regexes in another? That'd be much easier to review than trying to
    see the whole thing at once.

4. We use a number of linters to make our code better. Some of these are enforced by Github Actions, and others are not. The easiest way to do your work is to use [pre-commit][pc].

    You can run pre-commit with:

        docker exec -it cl-django pre-commit run --all-files

    You might also want to install it locally. If you do that, you can make it run automatically every time you do a commit, as a "pre-commit hook" (hence the name).

    However you run it, when you do it'll run a bunch of linters including `black`, `isort`, and `flynt`. Unfortunately, `pre-commit` doesn't work well with `mypy`, but that'll need to pass too. More on that below.

[pc]: https://pre-commit.com/

1. We use the [black][black] code formatter to make sure all our Python code
has the same formatting. This is an automated tool that you *must* run on any
code you run before you push it to Github. When you run it, it will reformat
your code. We recommend [integrating it into your editor][black-ed].

    Beyond what black will do for you by default, if you somehow find a way to
    do whitespace or other formatting changes, do so in their own commit and
    ideally in its own PR. When whitespace is combined with other code changes,
    the PR's become impossible to read and risky to merge. This is a big reason
    we use black.

1. We are beginning to use mypy to add type hints to our Python code. New code should include hints, and updates to old code should add hints to the old code. The idea is for our hints to gradually get better and more complete. Our Github Action for mypy is in `lint.yml`, and should be updated to run against any areas that have hints. This just takes a second once mypy is working properly on a file or module.

1. We use `iSort` to sort our imports. If your imports aren't sorted properly,
iSort will tell you so when you push your code to Github. Again, we recommend
getting iSort integrated into your editor or workflow.

1. We have an editorconfig, an eslint configuration, and a black configuration.
Please use them.

1. We do not yet have a Code of Conduct, but we do have [our employee
manual][hr], and we expect all our employees and volunteers to abide by it.

Some of these guidelines are a little sloppy compared with many projects. Those
projects have greater quality needs, are popular enough to demand a high
bar, and can envision coding techniques as a part of their overall goal. We
don't have to lead the industry with our approach, we just need to get good
work done. That's the goal here.


### Special notes for special types of code

1. If your PR includes a migration of the DB, we need SQL files for those migrations. These can be easily made with the `sqlmigrate` command. See MIGRATIONS.md as well for details on smart migration files and why this is needed.

2. If you alter any react code, include minified builds and map files of the new JS in your PR so that they can be deployed. While developing, you will have non-minified versions of these files. To build the minified versions, do:

        npm run build

[me]: https://github.com/mlissner
[flow]: https://guides.github.com/introduction/flow/
[bdfl]: https://en.wikipedia.org/wiki/Benevolent_dictator_for_life
[format]: https://github.com/angular/angular.js/blob/master/DEVELOPERS.md#-git-commit-guidelines
[format-plugin]: https://plugins.jetbrains.com/plugin/9861-git-commit-template/
[hr]: https://github.com/freelawproject/hr/blob/main/handbook/handbook.md
[black]: https://black.readthedocs.io/en/stable/
[black-ed]: https://black.readthedocs.io/en/stable/editor_integration.html


## Adding a new dependency

We use Poetry as our Python package manager instead of pip. It's pretty good, but nobody is used to it yet. It has very good docs you should use for everyday stuff, but the one thing to know about it is that to use it you need to shell into the docker image.

So, once the docker image is running, do something like this:

    docker exec -it cl-django bash

Once you're inside the image, you'll then be able to do:

    poetry add some-new-package

That will do two things. First, it will add the dependency while you're using the container. That's cool, but will go away if you restart docker or the container. The second thing it does is update pyproject.toml and poetry.lock. With that done, you can make new docker images as described by the README's in the docker folders.


## Testing

Any time you're contributing to or hacking on code base, whether adding features or fixing issues, you should validate your changes don't break core functionality by executing the test suite. This is also a great way to validate your development environment is properly configured. You should also add new tests for your new feature or fix.

In general, the easiest way to run the test suite is via Django's `test` command. In docker, that's:

```bash
docker exec -it cl-django python /opt/courtlistener/manage.py test cl --exclude-tag selenium --keepdb
```

The `cl` parameter is the name of the Python package to search for tests. It's not required, but a good habit to learn as you can more specifically specify tests by providing more details. For example:

 - `cl.search` to execute only tests in the search module, or...
 - `cl.search.tests.SearchTest` to run a particular test class, or...
 - `cl.search.tests.SearchTest.test_a_simple_text_query` to run a particular test.

Also:

`--exclude-tag selenium` is used to exclude selenium tests during local development. They'll be run on CI and they take a while, so it's sort of best not to bother with them most of the time.

`--keepdb` will keep your database between tests, a big speed up.

We use a custom test runner to make our tests a even faster:

 1. By default, it disables output aside from warnings. This makes tests slightly faster. You can enable output with our special command, `--enable-logging`.

 1. By default, it runs tests in parallel. Normally, you have to use the `--parallel` flag of the test command to do this, but developers forget. No more. If you want to override this so your tests run on a single core (why would you?) you could pass `--parallel=1`.

 1. No matter how many databases you have configured in your settings, only one is used during tests. This makes tests faster since they don't have to mess around with transactions in databases that aren't even used.

 1. When you use `--keepdb`, if your database was not deleted because the last run crashed, it will delete it for you. Ahhh.

 1. We use custom test classes (see below) and our runner blocks you from using other test classes.

For more details, Django provides a lot of documentation on [testing in Django][django-testing]. Make sure to read the docs related to the current release used in CourtListener.

This can also be set up using Intellij and a Docker compose file.


### About the Types of Tests

There are a few different types of tests in the CourtListener test suite and can be generally categorized as follows in increasing complexity:

* **Unit Tests** that exercise core application logic and may require some level of access to the Django test database,

* **Solr Tests** that rely on the Apache Solr test cores to be online and have documents indexed for test execution,

* **Selenium Tests** that rely on the full-stack of Django, the database, and Solr to be available in order to test from the point of view of a web browser accessing the application.

#### Unit Tests

Unit tests all derive from the classes in `cl.tests.cases`. Typically, they will not need database access, and should thus use `cl.tests.cases.SimpleTestCase`. If possible, these should run without a functioning Solr, Postgresql, or Selenium environment.

These are the bread and butter of validating functions and business logic. You should contribute these when you write any new functions or update them when enhancing existing functions.

#### Solr Tests

Solr/search tests should derive from `cl.search.tests.EmptySolrTestCase` and use appropriate setup/teardown methods to populate the index by either manually creating model instances and passing the `index=True` attribute when calling `.save()` or calling the provided `cl.search.management.commands.cl_update_index` Django management command that will index the models from the database into the Solr cores.

#### Selenium Tests

Selenium tests should derive from `cl.tests.base.BaseSeleniumTest`, which automatically handles the setup and teardown of a Selenium webdriver instance available at `self.browser` from within your test code.

There are some helper methods provided via `BaseSeleniumTest` as well:
* `reset_browser()` - start a new browser session
* `click_link_for_new_page(link_text, timeout)` - a wrapper around the Selenium functions for finding an anchor based on the anchor text and calling click(), but also does an explicit wait up until _timeout_ seconds for the browser page to change. Use when expecting a navigation event.
* `attempt_sign_in(username, password)` - from a given CL page, will attempt to use the _Sign in / Register_ link and input the given username and password.
* `get_url_and_wait(url, timeout)` - will input the given url into the browser's address bar, submit, and wait until _timeout_ seconds for the given url to load.
* `assert_text_in_body(text)` - attempts to find the given text in the body of the current web page, failing the test if not found
* `assert_text_not_in_body(text)` - similar to previous, but tests that text is NOT in the body, failing if it's found.
* `extract_result_count_from_serp()` - if on the search result page, will attempt to find and parse the total results found count into a number and return it.

*Windows/WSL Tip:* If you are running tests on a Windows machine with WSL you probably hit a wall because we don't have a /dev/shm directory and this won't let you run the selenium tests. To fix this: you need to get the full path to /dev/shm or /run/shm from your WSL virtual machine, in my case is: *\\wsl.localhost\Ubuntu-20.04\run\shm* (you can get this path from Windows explorer), the next thing to do is to set the environment variable *CL_SHM_DIR* to that path and then restart your *cl-selenium* container.

##### Viewing the Remote Selenium Browser

You can watch the remote selenium browser using VNC. To do so, start a VNC client, and then connect to:

    0.0.0.0:5900

The password is `secret`. Make sure that `SELENIUM_HEADLESS` is set to `False` or else you'll see nothing.

With those things done, run some tests and watch as it goes!

##### Increasing the Test Timeouts

The Selenium tests are wrapped with a timeout annotation that will fail them if they take too long to run. If you need to increase, or even want to decrease, this value then the easiest step is to set the `SELENIUM_TIMEOUT` environment variable to the given time in seconds.

For example, for a 2 minute timeout, you might do the following on Linux (or within the FreeLawBox):

```bash
export SELENIUM_TIMEOUT=120
```

##### Taking Screenshots on Failure

While a little flaky at the moment, most Selenium tests will be able to take a screenshot of the browser window on a failure.

To enable screenshots, simply define a `SELENIUM_DEBUG` environment variable set to anything. It's presence indicates it's enabled.

```bash
export SELENIUM_DEBUG=1
```

That will create screenshots at the end of every test as part of the `tearDown` method. If you want screenshots at other times, you can always add a line like:

    self.browser.save_screenshot('/tmp/' + filename)

Screenshots will be saved into the `cl-django` container. To grab them, [you can use][cp] `docker cp`. On GitHub, *if* the tests fail, these are stored as an "artifact" of the build, and you can download them to inspect them.

[cp]: https://stackoverflow.com/a/22050116/64911

### Celery debugging

If you are working with [celery tasks](https://docs.celeryq.dev/en/stable/userguide/monitoring.html#celery-events-curses-monitor), it's helpful to use celery events which is a simple curses monitor displaying task and worker history, you can inspect the result and traceback of tasks, and it also supports some management commands like rate limiting and shutting down workers.

1. First, you need to set `CELERY_TASK_ALWAYS_EAGER` to `False` under DEVELOPMENT Settings: `cl.settings.third_party.celery`, to allow running your task into the async worker:
`CELERY_TASK_ALWAYS_EAGER = False`
 Remember to set it `TRUE` once debugging is finished, otherwise, tests aren't going to pass.

2. To use celery events you need to run a celery worker that sends events, adding the `-E` option:
`docker exec -it cl-celery celery -A cl worker -c 1 -E`

3. Then start `celery events` monitor:
`docker exec -it cl-celery celery -A cl events`
Now, when executing a task you'll be able to monitor it with celery events.

### How to update a docker image.

Once an amazing new feature has been added to CL or to an import dependency (ie Juriscraper) one might need to update the docker image.

Use CI/CD to do this automatically (see below), or if you're impatient:

1) Push to `main`

2) Build and push new images with `make push --file docker/django/Makefile`


### CI/CD

We use Github Actions to run the full test and linting suite on every push. If the tests fail or your code is not formatted properly according to our linters, your code probably won't get merged.

When code is merged into `main`, we also automatically build and push new docker images, then deploy that code to our kubernetes cluster. If the code has a database migration, it is not deployed without manual review and a re-run of the deploy step after the migration is applied by hand.


[wiki]: https://github.com/freelawproject/courtlistener/wiki/Installing-CourtListener-on-Ubuntu-Linux
[chromedriver]: https://sites.google.com/a/chromium.org/chromedriver/downloads
[django-testing]: https://docs.djangoproject.com/en/1.8/topics/testing/
[hub-cl-testing]: https://hub.docker.com/r/freelawproject/courtlistener-testing/
[hub-flp]: https://hub.docker.com/u/freelawproject/dashboard/
[dr]: https://github.com/freelawproject/doctor/
[env]: https://django-environ.readthedocs.io/en/latest/index.html
[3]: https://12factor.net/config
[ghd]: https://github.com/freelawproject/courtlistener/discussions
