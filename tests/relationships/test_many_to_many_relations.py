import os
import datetime

import sqlalchemy as sa
from pytest import mark
from sqlalchemy_history import versioning_manager

from tests import TestCase, create_test_cases


class ManyToManyRelationshipsTestCase(TestCase):
    def create_models(self):
        class Article(self.Model):
            __tablename__ = "article"
            __versioned__ = {"base_classes": (self.Model,)}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        article_tag = sa.Table(
            "article_tag",
            self.Model.metadata,
            sa.Column(
                "article_id",
                sa.Integer,
                sa.ForeignKey("article.id"),
                primary_key=True,
            ),
            sa.Column("tag_id", sa.Integer, sa.ForeignKey("tag.id"), primary_key=True),
            sa.Column(
                "created_date",
                sa.DateTime,
                nullable=False,
                server_default=sa.func.current_timestamp(),
                default=datetime.datetime.utcnow,
            ),
        )

        class Tag(self.Model):
            __tablename__ = "tag"
            __versioned__ = {"base_classes": (self.Model,)}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        Tag.articles = sa.orm.relationship(Article, secondary=article_tag, backref="tags")

        self.Article = Article
        self.Tag = Tag

    def test_version_relations(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        self.session.add(article)
        self.session.commit()
        assert not article.versions[0].tags

    def test_single_insert(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        tag = self.Tag(name="some tag")
        article.tags.append(tag)
        self.session.add(article)
        self.session.commit()
        assert len(article.versions[0].tags) == 1

    def test_unrelated_change(self):
        tag1 = self.Tag(name="some tag")
        tag2 = self.Tag(name="some tag2")

        self.session.add(tag1)
        self.session.add(tag2)
        self.session.commit()

        article1 = self.Article(
            name="Some article",
        )
        article1.name = "Some article"
        self.session.add(article1)
        article1.tags.append(tag1)

        self.session.commit()

        article2 = self.Article()
        article2.name = "Some article2"
        self.session.add(article2)
        article2.tags.append(tag1)

        self.session.commit()

        article1.name = "Some other name"
        self.session.commit()

        assert len(article1.versions[1].tags) == 1

    def test_multi_insert(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        tag = self.Tag(name="some tag")
        article.tags.append(tag)
        article.tags.append(self.Tag(name="another tag"))
        self.session.add(article)
        self.session.commit()
        assert len(article.versions[0].tags) == 2

    def test_collection_with_multiple_entries(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        self.session.add(article)
        article.tags = [self.Tag(name="some tag"), self.Tag(name="another tag")]
        self.session.commit()
        assert len(article.versions[0].tags) == 2

    def test_delete_single_association(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        tag = self.Tag(name="some tag")
        article.tags.append(tag)
        self.session.add(article)
        self.session.commit()
        article.tags.remove(tag)
        article.name = "Updated name"
        self.session.commit()
        tags = article.versions[1].tags
        assert len(tags) == 0

    def test_delete_multiple_associations(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        tag = self.Tag(name="some tag")
        tag2 = self.Tag(name="another tag")
        article.tags.append(tag)
        article.tags.append(tag2)
        self.session.add(article)
        self.session.commit()
        article.tags.remove(tag)
        article.tags.remove(tag2)
        article.name = "Updated name"
        self.session.commit()
        assert len(article.versions[1].tags) == 0

    def test_remove_node_but_not_the_link(self):
        article = self.Article()
        article.name = "Some article"
        article.content = "Some content"
        tag = self.Tag(name="some tag")
        article.tags.append(tag)
        self.session.add(article)
        self.session.commit()
        self.session.delete(tag)
        article.name = "Updated name"
        self.session.commit()
        tags = article.versions[1].tags
        assert len(tags) == 0

    def test_multiple_parent_objects_added_within_same_transaction(self):
        article = self.Article(name="Some article")
        tag = self.Tag(name="some tag")
        article.tags.append(tag)
        self.session.add(article)
        article2 = self.Article(name="Some article")
        tag2 = self.Tag(name="some tag")
        article2.tags.append(tag2)
        self.session.add(article2)
        self.session.commit()
        article.tags.remove(tag)
        self.session.commit()
        self.session.refresh(article)
        tags = article.versions[0].tags
        assert tags == [tag.versions[0]]

    def test_relations_with_varying_transactions(self):
        # one article with one tag
        article = self.Article(name="Some article")
        tag1 = self.Tag(name="some tag")
        article.tags.append(tag1)
        self.session.add(article)
        self.session.commit()

        # update article and tag, add a 2nd tag
        tag2 = self.Tag(name="some other tag")
        article.tags.append(tag2)
        tag1.name = "updated tag1"
        article.name = "updated article"
        self.session.commit()

        # update article and first tag only
        tag1.name = "updated tag1 x2"
        article.name = "updated article x2"
        self.session.commit()

        assert len(article.versions[0].tags) == 1
        assert article.versions[0].tags[0] is tag1.versions[0]

        assert len(article.versions[1].tags) == 2
        assert tag1.versions[1] in article.versions[1].tags
        assert tag2.versions[0] in article.versions[1].tags

        assert len(article.versions[2].tags) == 2
        assert tag1.versions[2] in article.versions[2].tags
        assert tag2.versions[0] in article.versions[2].tags


create_test_cases(ManyToManyRelationshipsTestCase)


class TestManyToManyRelationshipWithViewOnly(TestCase):
    def create_models(self):
        class Article(self.Model):
            __tablename__ = "article"
            __versioned__ = {"base_classes": (self.Model,)}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        article_tag = sa.Table(
            "article_tag",
            self.Model.metadata,
            sa.Column(
                "article_id",
                sa.Integer,
                sa.ForeignKey("article.id"),
                primary_key=True,
            ),
            sa.Column("tag_id", sa.Integer, sa.ForeignKey("tag.id"), primary_key=True),
        )

        class Tag(self.Model):
            __tablename__ = "tag"
            __versioned__ = {"base_classes": (self.Model,)}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        Tag.articles = sa.orm.relationship(Article, secondary=article_tag, viewonly=True)

        self.article_tag = article_tag
        self.Article = Article
        self.Tag = Tag

    def test_does_not_add_association_table_to_manager_registry(self):
        assert self.article_tag not in versioning_manager.version_table_map


class TestManyToManySelfReferential(TestCase):
    def create_models(self):
        class Article(self.Model):
            __tablename__ = "article"
            __versioned__ = {}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        article_references = sa.Table(
            "article_references",
            self.Model.metadata,
            sa.Column(
                "referring_id",
                sa.Integer,
                sa.ForeignKey("article.id"),
                primary_key=True,
            ),
            sa.Column("referred_id", sa.Integer, sa.ForeignKey("article.id"), primary_key=True),
        )

        Article.references = sa.orm.relationship(
            Article,
            secondary=article_references,
            primaryjoin=Article.id == article_references.c.referring_id,
            secondaryjoin=Article.id == article_references.c.referred_id,
            backref="cited_by",
        )

        self.Article = Article
        self.referenced_articles_table = article_references

    def test_single_insert(self):
        article = self.Article(name="article")
        reference1 = self.Article(name="referred article 1")
        article.references.append(reference1)
        self.session.add(article)
        self.session.commit()

        assert len(article.versions[0].references) == 1
        assert reference1.versions[0] in article.versions[0].references

        assert len(reference1.versions[0].cited_by) == 1
        assert article.versions[0] in reference1.versions[0].cited_by

    def test_multiple_inserts_over_multiple_transactions(self):
        # create 1 article with 1 reference
        article = self.Article(name="article")
        reference1 = self.Article(name="reference 1")
        article.references.append(reference1)
        self.session.add(article)
        self.session.commit()

        # update existing, add a 2nd reference
        article.name = "Updated article"
        reference1.name = "Updated reference 1"
        reference2 = self.Article(name="reference 2")
        article.references.append(reference2)
        self.session.commit()

        # update only the article and reference 1
        article.name = "Updated article x2"
        reference1.name = "Updated reference 1 x2"
        self.session.commit()

        assert len(article.versions[1].references) == 2
        assert reference1.versions[1] in article.versions[1].references
        assert reference2.versions[0] in article.versions[1].references

        assert len(reference1.versions[1].cited_by) == 1
        assert article.versions[1] in reference1.versions[1].cited_by

        assert len(reference2.versions[0].cited_by) == 1
        assert article.versions[1] in reference2.versions[0].cited_by

        assert len(article.versions[2].references) == 2
        assert reference1.versions[2] in article.versions[2].references
        assert reference2.versions[0] in article.versions[2].references

        assert len(reference1.versions[2].cited_by) == 1
        assert article.versions[2] in reference1.versions[2].cited_by


@mark.skipif(os.environ.get("DB") == "sqlite", reason="sqlite doesn't have a concept of schema")
class TestManyToManySelfReferentialInOtherSchema(TestManyToManySelfReferential):
    def create_models(self):
        class Article(self.Model):
            __tablename__ = "article"
            __versioned__ = {}
            __table_args__ = {"schema": "other"}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        article_references = sa.Table(
            "article_references",
            self.Model.metadata,
            sa.Column(
                "referring_id",
                sa.Integer,
                sa.ForeignKey("other.article.id"),
                primary_key=True,
            ),
            sa.Column("referred_id", sa.Integer, sa.ForeignKey("other.article.id"), primary_key=True),
            schema="other",
        )

        Article.references = sa.orm.relationship(
            Article,
            secondary=article_references,
            primaryjoin=Article.id == article_references.c.referring_id,
            secondaryjoin=Article.id == article_references.c.referred_id,
            backref="cited_by",
        )

        self.Article = Article
        self.referenced_articles_table = article_references

    def create_tables(self):
        try:
            self.connection.execute(sa.text("DROP SCHEMA IF EXISTS other"))
            self.connection.execute(sa.text("CREATE SCHEMA other"))
        except sa.exc.DatabaseError:  # pragma: no cover
            try:
                # Create a User for Oracle DataBase as it does not have concept of schema
                # ref: https://stackoverflow.com/questions/10994414/missing-authorization-clause-while-creating-schema # noqa E501
                self.connection.execute(sa.text("CREATE USER other identified by other"))
                # need to give privilege to create table to this new user
                # ref: https://stackoverflow.com/questions/27940522/no-privileges-on-tablespace-users
                self.connection.execute(sa.text("GRANT UNLIMITED TABLESPACE TO other"))
            except sa.exc.DatabaseError as dbe:
                if (
                    "ORA-01920: user name 'OTHER' conflicts with another user or role name"
                    not in dbe.__str__()
                ):
                    # NOTE: prior to oracle 23c we don't have concept of if not exists
                    #       so we just try to create if fails we continue
                    raise
        finally:
            try:
                # NOTE: Sqlalchemy >= 2.0.0 requires user to explicitly do commit for a given transaction
                # ref: https://docs.sqlalchemy.org/en/20/core/connections.html#commit-as-you-go
                self.connection.commit()
            except AttributeError:
                # Sqlalchemy < 2.0.0 does not have commit available to connection as executes does commit
                # automatically for a given ongoing transaction.
                pass

        TestManyToManySelfReferential.create_tables(self)


@mark.skipif(os.environ.get("DB") == "sqlite", reason="sqlite doesn't have a concept of schema")
class TestManyToManyRelationshipsInOtherSchemaTestCase(ManyToManyRelationshipsTestCase):
    def create_models(self):
        class Article(self.Model):
            __tablename__ = "article"
            __versioned__ = {"base_classes": (self.Model,)}
            __table_args__ = {"schema": "other"}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        article_tag = sa.Table(
            "article_tag",
            self.Model.metadata,
            sa.Column(
                "article_id",
                sa.Integer,
                sa.ForeignKey("other.article.id"),
                primary_key=True,
            ),
            sa.Column("tag_id", sa.Integer, sa.ForeignKey("other.tag.id"), primary_key=True),
            schema="other",
        )

        class Tag(self.Model):
            __tablename__ = "tag"
            __versioned__ = {"base_classes": (self.Model,)}
            __table_args__ = {"schema": "other"}

            id = sa.Column(
                sa.Integer, sa.Sequence(f"{__tablename__}_seq", start=1), autoincrement=True, primary_key=True
            )
            name = sa.Column(sa.Unicode(255))

        Tag.articles = sa.orm.relationship(Article, secondary=article_tag, backref="tags")

        self.Article = Article
        self.Tag = Tag

    def create_tables(self):
        try:
            self.connection.execute(sa.text("DROP SCHEMA IF EXISTS other"))
            self.connection.execute(sa.text("CREATE SCHEMA other"))
        except sa.exc.DatabaseError:
            try:
                # Create a User for Oracle DataBase as it does not have concept of schema
                # ref: https://stackoverflow.com/questions/10994414/missing-authorization-clause-while-creating-schema # noqa E501
                self.connection.execute(sa.text("CREATE USER other identified by other"))
                # need to give privilege to create table to this new user
                # ref: https://stackoverflow.com/questions/27940522/no-privileges-on-tablespace-users
                self.connection.execute(sa.text("GRANT UNLIMITED TABLESPACE TO other"))  # pragma: no cover
            except sa.exc.DatabaseError as dbe:  # pragma: no cover
                if (
                    "ORA-01920: user name 'OTHER' conflicts with another user or role name"
                    not in dbe.__str__()
                ):
                    # NOTE: prior to oracle 23c we don't have concept of if not exists
                    #       so we just try to create if fails we continue
                    raise
        finally:
            try:
                # NOTE: Sqlalchemy >= 2.0.0 requires user to explicitly do commit for a given transaction
                # ref: https://docs.sqlalchemy.org/en/20/core/connections.html#commit-as-you-go
                self.connection.commit()
            except AttributeError:
                # Sqlalchemy < 2.0.0 does not have commit available to connection as executes does commit
                # automatically for a given ongoing transaction.
                pass
        ManyToManyRelationshipsTestCase.create_tables(self)


create_test_cases(TestManyToManyRelationshipsInOtherSchemaTestCase)
