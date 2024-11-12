from pydantic import Field
from typing import Dict, Any
from bson import ObjectId

from eve.mongo import MongoModel, VersionableMongoModel
from test_base import TestModel, InnerModel



def test_mongo_document():
    """
    Test save, load, and update
    """

    class MongoModelTest(MongoModel):
        num: int = Field(ge=1, le=10, default=1)
        args: Dict[str, Any]
        user: ObjectId

        @classmethod
        def get_collection_name(cls) -> str:
            return "stories"

    t = MongoModelTest(
        env="STAGE", 
        num=2,
        args={"foo": "bar"}, 
        user=ObjectId("666666663333366666666666")
    )

    t.save()

    t2 = MongoModelTest.load(t.id, env="STAGE")

    assert t2 == MongoModelTest(
        env="STAGE", 
        num=2, 
        args={"foo": "bar"}, 
        user=ObjectId("666666663333366666666666"), 
        id=t.id, 
        createdAt=t.createdAt, 
        updatedAt=t.updatedAt
    )

    t2.update(invalid_arg="this is ignored", num=7, args={"foo": "hello world"})

    t3 = MongoModelTest.load(t2.id, env="STAGE")

    assert t.id == t2.id == t3.id

    assert t3 == MongoModelTest(env="STAGE", num=7, args={"foo": "hello world"}, user=ObjectId("666666663333366666666666"), id=t2.id, createdAt=t2.createdAt, updatedAt=t2.updatedAt)


def test_versionable_base_model():
    """
    Test versionable base model saving, loading, and applying edits
    """

    t1 = VersionableMongoModel(
        instance = TestModel(
            string_field="hello world 11", 
            string_list_field=["test1", "test2"], 
            dict_field={"test3": "test4"},
            base_model_field=InnerModel(string_field="test5", number_field=7)
        ),
        collection_name="stories",
        env="STAGE"
    )

    t1.save()

    TestModelEdit = t1.get_edit_model()

    t1_edit = TestModelEdit(
        edit_string_field="test6",
        add_string_list_field={"index": 1, "value": "test8"},
        edit_dict_field={"test3": "test11"},
        add_dict_field={"test12": "test13"},
        edit_base_model_field={"string_field": "test14"}
    )

    t1.apply_edit(t1_edit)
    
    t1.save()

    t1_expected = TestModel(
        string_field="test6",
        string_list_field=["test1", "test8", "test2"],
        dict_field={"test3": "test11", "test12": "test13"},
        base_model_field=InnerModel(
            string_field="test14", 
            number_field=7
        )
    )

    assert t1.current == t1_expected

    t2 = VersionableMongoModel.load(t1.id, collection_name="stories", env="STAGE")

    t2_edit = TestModelEdit(
        edit_string_field="test4999",
        add_string_list_field={"index": 1, "value": "test4"},
        add_dict_field={"test4": "test56"},
        edit_base_model_field={"string_field": "test6", "number_field": 3}
    )

    t2.apply_edit(t2_edit)

    t2_expected = TestModel(
        string_field="test4999",
        string_list_field=["test1", "test4", "test8", "test2"],
        dict_field={"test3": "test11", "test12": "test13", "test4": "test56"},
        base_model_field=InnerModel(string_field="test6", number_field=3)
    )

    assert t2.current.model_dump() == t2_expected.model_dump()
    
    t2.save()

    t3 = VersionableMongoModel.load(t1.id, collection_name="stories", env="STAGE")

    t3_edit = TestModelEdit(
        edit_string_list_field={"index": 1, "value": "test99"},
        remove_dict_field="test2",
        edit_base_model_field={"string_field": "test72", "number_field": 4}
    )

    t3.apply_edit(t3_edit)

    t3_expected = TestModel(
        string_field="test4999",
        string_list_field=["test1", "test99", "test8", "test2"],
        dict_field={"test3": "test11", "test12": "test13","test4": "test56"},
        base_model_field=InnerModel(string_field="test72", number_field=4) 
    )

    assert t3.current.model_dump() == t3_expected.model_dump()

    t3.save()

    t4 = VersionableMongoModel.load(t1.id, collection_name="stories", env="STAGE")

    assert t4.current.model_dump() == t3_expected.model_dump()



# test_mongo_document()

# test_versionable_base_model()
