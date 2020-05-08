mapping = {
    "settings": {
        "number_of_shards" : 1
    },
    "mappings" : {
        "_source":{
            "excludes": [
                "content"
            ]
      },
      "properties" : {
        "content" : {
          "type" : "text"
        },
        "created" : {
          "type" : "date"
        },
        "described_by" : {
          "type" : "keyword"
        },
        "files" : {
          "type" : "nested",
          "properties" : {
            "checksum" : {
              "type" : "keyword"
            },
            "id" : {
              "type" : "keyword"
            },
            "mime_type" : {
              "type" : "keyword"
            },
            "path" : {
              "type" : "keyword"
            },
            "size" : {
              "type" : "long"
            },
            "type" : {
              "type" : "keyword"
            },
            "urn" : {
              "type" : "keyword"
            }
          }
        },
        "id" : {
          "type" : "keyword",
          "store" : True
        },
        "label" : {
          "type" : "text",
          "fields" : {
            "raw" : {
              "type" : "keyword"
            }
          }
        },
        "meta" : {
          "properties" : {
            "created" : {
              "type" : "text",
              "fields" : {
                "raw" : {
                  "type" : "keyword",
                  "ignore_above" : 256
                }
              }
            },
            "title" : {
              "type" : "text",
              "fields" : {
                "raw" : {
                  "type" : "keyword",
                  "ignore_above" : 256
                }
              }
            }
          }
        },
        "package_version" : {
          "type" : "keyword"
        },
        "patch" : {
          "type" : "keyword"
        },
        "patches" : {
          "type" : "keyword"
        },
        "see_also" : {
          "type" : "keyword"
        },
        "size" : {
          "type" : "long"
        },
        "status" : {
          "type" : "keyword"
        },
        "tags" : {
          "type" : "keyword"
        },
        "type" : {
          "type" : "keyword"
        },
        "urn" : {
          "type" : "keyword"
        },
        "version" : {
          "type" : "keyword"
        }
      }
    }
}

content_mapping = {
    "settings": {
        "number_of_shards" : 1
    },
    "mappings" : {
        "_source":{
            "excludes": [
                "content"
            ]
      },
      "properties" : {
        "id" : {
          "type" : "keyword",
          "store" : True
        },
        "type" : {
          "type" : "keyword",
          "store": True
        },
        "path" : {
          "type" : "keyword",
          "store" : True
        },
        "image" : {
          "type" : "keyword",
          "store" : True
        },
        "tag" : {
          "type" : "keyword"
        },
        "content" : {
          "type" : "text"
        },
        "size" : {
          "type" : "long"
        },
        "meta" : {
          "properties" : {
            "created" : {
              "type" : "text",
              "fields" : {
                "raw" : {
                  "type" : "keyword",
                  "ignore_above" : 256
                }
              }
            },
            "title" : {
              "type" : "text",
              "fields" : {
                "raw" : {
                  "type" : "keyword",
                  "ignore_above" : 256
                }
              }
            }
          }
        },
        "label" : {
          "type" : "text",
          "fields" : {
            "raw" : {
              "type" : "keyword"
            }
          }
        }
      }
    }
}

