# Install Guide

## 1. Install python

https://www.python.org/ftp/python/

We've tested in py 3.10.5 and py 3.14.2

## 2. Install requirements

```cmd
pip install -r requirements.txt
```

## 3. Download nodejs

https://nodejs.org/en/download

## 4. Install typescript

```
npm install -g typescript
```

## 5. Compile ts to js

On Windows, double click to run "\public\js\watch.bat"

On macOS and Linux, run the same command directly:

```sh
cd public/js
tsc --watch
```

## 6. Download assets

You need to download the game to gain its `assets` folder from [itch.io](https://irefrixs.itch.io/marvel-lcg) and put it in the root folder of this project

## 7. Start the game

```
py main.py
```

## 8. Optional: fetch the card art up front

Card faces the `assets` folder does not carry are downloaded from a card server
the first time each one is shown, one request at a time, which is what makes a
first session slow. This walks `sets_info.json` to every scenario and hero it
lists and downloads all of it in one go instead, then exits:

```
py main.py -prefetch_images
```

It skips anything already in `assets`, so it is safe to re-run after an update,
and `-prefetch_workers 16` will pull harder if your connection can take it.

