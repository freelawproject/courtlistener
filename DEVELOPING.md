# Developing in CourtListener

CourtListener is built upon a few key pieces of technology that need to come together. Whether you're contributing platform code, web design, etc. it helps to know the easiest ways to run and test the project.

Historically, we have used [wiki instructions to get set up][wiki], but these days most things can be accomplished using docker.

But before we can get into that, we must address...


## Legal Matters

Not surprisingly, we have a lot of legal, and particularly IP, lawyers around here. As a result, we endeavor to be a model for other open source projects in how we handle IP contributions and concerns. 

We do this in a couple of ways. First, we use a copy-left license for CourtListener, the GNU GPL Affero license. Read the details in the license itself, but the high level is that it's a copy-left license for server code that isn't normally distributed to end users (like an app would be, say).

The other thing we do is require a contributor license agreement from any non-employees or non-contractors that contribute code to the project. You can find a form for this purpose in the root of our project. If you have any questions about it, please don't hesitate to ask.

On with the show.


## Set up

The major components of CourtListener are:

 - Postgresql - For database storage. We used to use MySQL long ago, but it caused endless weird and surprising problems. Postgresql is great.
 
 - Redis - For in-memory fast storage, caching, task queueing, some stats logging, etc. Everybody loves Redis for a reason. It's great.
 
 - Celery - For running asynchronous tasks. We've been using this a long time. It causes a lot of annoyance and sometimes will have unsolvable bugs, but as of 2019 it's better than any of the competition that we've tried. 
 
 - Tesseract - For OCR. It's getting good lately, which is nice since we convert hundreds of thousands of pages.
 
 - Solr - For making things searchable. It's *decent*. Our version is currently very old, but it hangs in there. We've also tried Sphinx a while back. We chose Sphinx early on literally because it had a smaller binary than Solr, and so seemed less intimidating (it was early times, and that logic might have been sound).
 
 - Python/Django/et al - And their associated bits and pieces.


### Pulling Everything Together

We use a docker compose file to make development easier. Don't use it for production! It's not secure enough and it uses bad practices for data storage. But if you're a dev, it should work nicely. To use it, you need do a few things:

 - Create the bridge network it relies on:
 
        docker network create -d bridge --attachable cl_net_overlay
        
    This is important so that each service in the compose file can have a hostname.

 - Make sure that in your CourtListener settings, you've set up the following (these should all be defaults):
 
     - `REDIS_HOST` should be `cl-redis`.
     - `SOLR_HOST` should be `http://cl-solr:8983`. 
     - `DOCKER_SELENIUM_HOST` should be `http://cl-selenium:4444/wd/hub`
     - `DOCKER_DJANGO_HOST` should be `cl-django`
     - The `default` database should not have host or port parameters (it uses unix sockets), and it should have a `USER` of `postgres` and a password of `postgres`.

    See below if you need an explanation of how settings work in CourtListener.

 - Update the group permissions of the solr repository so it can be mounted into the solr container and then accessed from within it. This is wonky, but I can't find a way around this. For the commands to run, see the README.md file in the solr repository.

The final command you'll run is:
    
      docker-compose up
         
(Make sure you're in the same directory as the docker-compose.yml file and it should work.)

There are a few optional variables that you can see if you peek inside the compose file. These give you a few opportunities to tweak things at runtime:

 - `CL_SOLR_CODE_DIR` is a path to the [`courtlistener-solr-server` repository's code][cl-solr]. This will default to a directory called `courtlistener-solr-server` that is next to the `courtlistener` repository on your file system, but if you put the solr repo somewhere else, you might set it to something like `/some/weird/location/courtlistener-solr-server`.

If that goes smoothly, it'll launch Solr, PostgreSQL, Redis, Celery (with access to Tesseract), Django, and a Selenium test server. Whew! 

You then need to do a few first time set ups:

1. Set up the DB. The first time you run this, it'll create the database for you, but you'll need to migrate it. To do so, you need to have the context of the CourtListener virtualenv and computer. You just launched those when you ran the docker compose file. To reach inside the correct docker image and migrate the models, run:

        docker exec -it cl-django python /opt/courtlistener/manage.py migrate
    
    That will run the command in the right place in the right way.

1. Whenever you create a new Django db, you need to create a super user. Do so with:

        docker exec -it cl_django python /opt/courtlistener/manage.py createsuperuser
 
So that should be it! You should now be able to access the following URLs:

 - <http://127.0.0.1:8000> - Your dev homepage
 - <http://127.0.0.1:8000/admin> - The Django admin page (try the super user)
 - <http://127.0.0.1:8983/solr> - Solr admin page
 - 127.0.0.1:5900 - A VNC server to the selenium machine (it doesn't serve http though)

[cl-solr]: https://github.com/freelawproject/courtlistener-solr-server


## How Settings Work in CourtListener

The files in the `cl/settings` directory contain all of the settings for CourtListener. They are read in alphabetical order, with each subsequent file potentially overriding the previous one.

Thus, `10-public.py` contains default settings for CourtListener and Celery. To override it, simply create a file in `cl/settings` called `11-private.py`. Since `11` comes after `10` *alphabetically*, it'll override anything in `10-*`. 

Files ending in `-public.py` are meant to be distributed in the code base. Those ending in `-private.py` are meant to stay on your machine. In theory, our `.gitignore` file will ignore them. 

You can find an example file to use for `11-private.py` in `cl/settings`. It should have the defaults you need, but it's worth reading through.

Files that are read later (with higher numbered file names) have access to the 
context of files that are read earlier. For example, if `01-some-name.py` 
contains:
 
    SOME_VAR = {'some-key': 'some-value'}
    
You could create a file called `02-my-overrides.py` that contained:

    SOME_VAR['some-key'] = 'some-other-value'
    
That is, you can assume that `SOME_VAR` exists because it was declared in an 
earlier settings file. Your IDE will likely complain that `SOME_VAR` doesn't 
exist in `02-my-overrides.py`, but ignore your IDE. If you want to read the 
code behind all this, look in `settings.py` (in the root directory). It's 
short.


## Guidelines for Contributions

For the most part, we use [Github flow][flow] to get our work done. Our 
[BDFL][bdfl] and primary developer is [@mlissner][me]. For better and/or for worse, 
he doesn't care too much about git, provided things get done smoothly and his 
life is fairly easy. What that means generally, is:

1. Commits should represent a unit of work. In other words, if you're working 
on a big feature, each commit should be a discrete step along the path of 
getting that feature ready to land. Bad or experimental work shouldn't be in a
commit that you submit as part of a PR, if you can avoid it. 

1. Your commit messages should use [the format defined by the Angular.js 
project][format]. This is pretty easy if you use [this plugin][format-plugin] 
for Intellij/PyCharm/et al.

1. If you want to change whitespace, do it in its own commit and ideally in its
own PR. We encourage code cleanup and whitespace/reformatting is part of that, 
BUT the more isolated it is from other changes, the better. When whitespace is
combined with other code changes, the PR's become impossible to read and risky
to merge. 

    A suggestion: If this stuff bugs you, do a round of whitespace/formatting 
    cleanup before you start on each file and/or once you're done.  

1. *KEEP YOUR PR's SMALL*. A good PR should land a specific thing of some sort. 
It doesn't have to be done — it doesn't even have to work! — but it should be 
clean and it should be your best effort at clean *progress*. PRs are both a way
of getting your work into the system and a way to *communicate* your work. The
latter is more important. 10 small, clean PRs are about 10× better than a 
monolithic one that is fully functional. 

    Say you are developing a system that relies on regexes to do something. Why
    not submit the regexes (and their tests!) in one PR and the thing that uses
    those regexes in another? That'd be much easier to review than trying to 
    see the whole thing at once. 

1. Finally, we have both an editorconfig and an eslint configuration. Please use them. 

These guidelines are a little sloppy compared with many projects. Those 
projects have greater quality needs, are popular enough to demand a high 
bar, and can envision coding techniques as a part of their overall goal. We 
don't have to lead the industry with our approach, we just need to get good 
work done. That's the goal here. 

[me]: https://github.com/mlissner
[flow]: https://guides.github.com/introduction/flow/
[bdfl]: https://en.wikipedia.org/wiki/Benevolent_dictator_for_life
[format]: https://github.com/angular/angular.js/blob/master/DEVELOPERS.md#-git-commit-guidelines
[format-plugin]: https://plugins.jetbrains.com/plugin/9861-git-commit-template/


## Testing

Any time you're contributing to or hacking on code base, whether adding features or fixing issues, you should validate your changes don't break the core functionality of CourtListener by executing the test suite. This is also a great way to validate your development environment is properly configured. (You should probably also add your own tests as well for your new feature.)

In general, the easiest way to run the test suite is via Django's `test` command. In docker, that's:

```bash
docker exec -it cl_django python /opt/courtlistener/manage.py test --noinput cl
```

The `--noinput` flag tells Django to destroy any old test databases without prompting for confirmation (typically this is what you want).

The `cl` parameter is the name of the Python package to search for tests. It's not required, but a good habit to learn as you can more specifically specify tests by provided more details, such as `cl.search` to execute only tests in the search module.

For more details, Django provides a lot of documentation on [testing in Django][django-testing]. Make sure to read the docs related to the current release used in CourtListener.

This can also be set up using Intellij and a Docker compose file.


### About the Types of Tests

There are a few different types of tests in the CourtListener test suite and can be generally categorized as follows in increasing complexity:

* **Unit Tests** that exercise core application logic and may require some level of access to the Django test database,

* **Solr Tests** that rely on the Apache Solr test cores to be online and have documents indexed for test execution,

* **Selenium Tests** that rely on the full-stack of Django, the database, and Solr to be available in order to test from the point of view of a web browser accessing the application.

#### Unit Tests

Unit tests should derive from `unittest.TestCase` or `django.test.TestCase` and run without a functioning Solr environment or Selenium functioning. These are the bread and butter of validating functions and business logic. You should contribute these when you write any new functions or update them when enhancing existing functions.

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
    
Screenshots will be saved into the `cl-django` container. To grab them, [you can use][cp] `docker cp`.

[cp]: https://stackoverflow.com/a/22050116/64911

### CI/CD

This Github project is configured to run tests for every pull request. A webhook triggers [CircleCI][circleci-cl-builds] to run `.circleci/config.yml`. `config.yml` makes CircleCI run tests inside a Docker container. The custom Docker image used to run tests is built from `.circleci/Dockerfile` and pushed to [Docker Hub][hub-cl-testing].

This currently needs to be upgraded to use our new docker compose files.


#### Updating the testing container

If you add new dependencies, remember to update the testing container with the following steps.

1. Have `docker` and `make` CLI tools installed.
2. Have a Docker Hub account that's a member of the [freelawproject organization][hub-flp].
3. `docker login` with your credentials for the Hub account above.
4. Set the version in `version.txt` to whatever makes sense according to
   semantic versioning. Most of the time incrementing the patch version is enough.
5. `make push --file .circleci/Makefile` 
6. Use new Docker image in CircleCI tests by updating the [tag in config.yml][circleci-test-container-tag].


[wiki]: https://github.com/freelawproject/courtlistener/wiki/Installing-CourtListener-on-Ubuntu-Linux
[chromedriver]: https://sites.google.com/a/chromium.org/chromedriver/downloads
[django-testing]: https://docs.djangoproject.com/en/1.8/topics/testing/
[vagrantfile]: https://raw.githubusercontent.com/freelawproject/freelawmachine/master/Vagrantfile
[vagrantfile-desktop]: https://github.com/freelawproject/freelawmachine/blob/master/Vagrantfile.desktop
[flm]: https://github.com/freelawproject/freelawmachine
[flm-readme]: https://github.com/freelawproject/freelawmachine/blob/master/README.md
[vagrant-ports]: https://www.vagrantup.com/docs/networking/forwarded_ports.html
[circleci-cl-builds]: https://circleci.com/gh/freelawproject/courtlistener
[hub-cl-testing]: https://hub.docker.com/r/freelawproject/courtlistener-testing/
[hub-flp]: https://hub.docker.com/u/freelawproject/dashboard/
[circleci-test-container-tag]: https://github.com/freelawproject/courtlistener/blob/360c259f7d427700c2de9bf8fd53a73a33ff2eed/.circleci/config.yml#L5
